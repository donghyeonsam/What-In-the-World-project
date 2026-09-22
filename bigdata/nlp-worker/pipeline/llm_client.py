"""vLLM 서버 호출 래퍼.

왜 별도 파일인가
  제목 번역과 본문 요약이 같은 서버를 쓴다. 타임아웃·재시도·추론모드 차단 같은
  공통 처리를 한 곳에 모아 두면, 모델을 바꾸거나 서버를 옮길 때 여기만 고치면 된다.

왜 모델을 프로세스 안에 올리지 않나
  예전 title_translation.py 는 Qwen 을 워커 프로세스에 직접 로드했다(약 16GB).
  vLLM 서버로 분리하면
    · 워커 재시작이 몇 초로 줄어든다 (모델을 다시 안 올린다)
    · 여러 요청을 GPU 가 알아서 겹쳐 처리한다 (continuous batching)
    · 모델 교체가 서버 재시작 한 번으로 끝난다
  대신 HTTP 호출이 하나 붙지만, 같은 기계 안(127.0.0.1)이라 비용이 없다.

포트를 18203 으로 쓰는 이유
  이 GPU 서버는 세 팀이 함께 쓴다. 8000 번은 Django·uvicorn·FastAPI·
  python -m http.server 가 전부 기본값으로 쓰는 번호라 충돌 위험이 크다.

  문제는 우리 서버가 떠 있는 동안이 아니다(포트는 배타적이라 남이 못 잡는다).
  24시간마다 프로세스가 정리되는 환경이라, 그 공백에 다른 팀이 같은 포트를
  잡으면 우리 워커가 '남의 서비스에 기사 본문을 보내고' 그 응답을 번역 결과로
  받아들인다. 에러가 안 나서 알아채기 어렵다.

  그래서 두 가지로 막는다.
    1. 아무도 기본값으로 쓰지 않는 포트 (18203 — 프로젝트 번호에서)
    2. 응답의 model 필드가 우리가 띄운 이름인지 확인 (verify_server / _check_model)

환경변수
    LLM_BASE_URL        기본 http://127.0.0.1:18203/v1
    LLM_MODEL           기본 news-llm  (vllm serve --served-model-name 과 맞출 것)
    LLM_TIMEOUT         기본 120초
    LLM_RETRIES         기본 2회 (총 3번 시도)
    LLM_ENABLE_THINKING 기본 0. 1 로 두면 추론 모드를 끄지 않는다(느려진다)
"""

from __future__ import annotations

import logging
import os
import random
import re
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://127.0.0.1:18203/v1").rstrip("/")
LLM_MODEL = os.getenv("LLM_MODEL", "news-llm")
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "120"))
LLM_RETRIES = int(os.getenv("LLM_RETRIES", "2"))
# Qwen3 계열은 추론 모드가 켜지면 <think> 블록을 먼저 뱉어 출력 토큰이 몇 배가 된다.
# 번역·요약에는 필요 없으므로 기본으로 끈다.
LLM_ENABLE_THINKING = os.getenv("LLM_ENABLE_THINKING", "0") not in ("0", "false", "False")

# 추론 모드가 꺼지지 않는 모델도 있어서, 출력에서도 한 번 더 걷어낸다.
_THINK_BLOCK = re.compile(r"<think\b[^>]*>.*?</think>\s*", re.S | re.I)
_ORPHAN_THINK = re.compile(r"^\s*<think\b[^>]*>.*$", re.S | re.I)

_session = requests.Session()
# 응답 모델 이름이 어긋났다는 경고는 한 번만 낸다(기사마다 찍히면 로그가 묻힌다)
_warned_model_mismatch = False


class LlmError(RuntimeError):
    """재시도까지 실패했을 때. 호출부가 기사 1건을 포기할지 정한다."""


def _check_model(data: dict[str, Any]) -> None:
    """응답이 우리가 띄운 모델에서 온 것인지 확인한다.

    포트를 다른 서비스가 잡고 있어도 형식만 맞으면 그럴듯한 응답이 온다.
    그 경우를 조용히 지나치지 않기 위한 확인이다. 다만 vLLM 버전에 따라
    model 필드 표기가 다를 수 있어, 막지는 않고 크게 한 번 경고한다.
    """
    global _warned_model_mismatch
    served = data.get("model")
    if not served or served == LLM_MODEL or _warned_model_mismatch:
        return
    _warned_model_mismatch = True
    logger.error(
        "LLM 응답의 모델 이름이 다릅니다: 기대 %r, 실제 %r (%s). "
        "다른 서비스가 이 포트를 쓰고 있을 수 있습니다. "
        "vllm serve --served-model-name 과 LLM_MODEL 을 확인하세요.",
        LLM_MODEL, served, LLM_BASE_URL,
    )


def strip_thinking(text: str) -> str:
    text = _THINK_BLOCK.sub("", text or "")
    # 닫는 태그 없이 잘린 경우 — 통째로 버린다(내용이 없다고 보는 편이 안전).
    if _ORPHAN_THINK.match(text):
        return ""
    return text.strip()


def health(timeout: float = 3.0) -> bool:
    """포트가 응답하는지만 본다. 누가 응답하는지는 모른다 — verify_server 를 쓸 것."""
    try:
        r = _session.get(f"{LLM_BASE_URL.rsplit('/v1', 1)[0]}/health", timeout=timeout)
        return r.status_code == 200
    except requests.RequestException:
        return False


def verify_server(timeout: float = 5.0) -> tuple[bool, str]:
    """그 포트에 있는 것이 '우리' vLLM 이 맞는지 확인한다.

    /v1/models 가 LLM_MODEL 을 돌려주는지 본다. 다른 팀 서비스가 같은 포트를
    잡았다면 여기서 걸린다. 워커 기동 전과 prompt_lab 실행 시 호출한다.
    """
    try:
        r = _session.get(f"{LLM_BASE_URL}/models", timeout=timeout)
    except requests.RequestException as exc:
        return False, f"연결 실패: {exc}"
    if r.status_code != 200:
        return False, f"/v1/models 가 {r.status_code} 를 돌려줌 — vLLM 이 아닙니다"
    try:
        served = [m.get("id") for m in (r.json().get("data") or [])]
    except ValueError:
        return False, "JSON 이 아닌 응답 — 다른 서비스가 이 포트를 쓰고 있습니다"
    if LLM_MODEL not in served:
        return False, (f"모델 이름이 다릅니다. 기대 {LLM_MODEL!r}, 실제 {served} "
                       f"— 다른 서비스이거나 --served-model-name 이 어긋났습니다")
    return True, f"{LLM_MODEL} @ {LLM_BASE_URL}"


def chat(
    system: str | None,
    user: str,
    *,
    max_tokens: int = 512,
    temperature: float = 0.0,
    timeout: float | None = None,
    retries: int | None = None,
    extra_body: dict[str, Any] | None = None,
) -> str:
    """메시지를 보내고 본문 텍스트를 돌려준다.

    system 에 None 을 주면 user 메시지 하나만 보낸다. 기존 프롬프트를 그대로
    유지해야 하는 호출부(title_translation)가 이 형태를 쓴다.

    system 을 쓸 경우, 모든 호출에 동일한 문자열을 넣는 것이 좋다. vLLM 의
    prefix caching 이 앞에서부터 같은 부분을 재사용하므로, 고정 지시문을 여기
    두면 기사마다 다시 계산하지 않는다.
    """
    timeout = LLM_TIMEOUT if timeout is None else timeout
    retries = LLM_RETRIES if retries is None else retries

    messages: list[dict[str, str]] = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": user})

    payload: dict[str, Any] = {
        "model": LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if not LLM_ENABLE_THINKING:
        # vLLM 이 채팅 템플릿에 그대로 넘긴다. 템플릿이 이 인자를 모르면 무시된다.
        payload["chat_template_kwargs"] = {"enable_thinking": False}
    if extra_body:
        payload.update(extra_body)

    url = f"{LLM_BASE_URL}/chat/completions"
    last: Exception | None = None

    for attempt in range(retries + 1):
        try:
            r = _session.post(url, json=payload, timeout=timeout)
            if r.status_code >= 500:
                raise LlmError(f"server {r.status_code}: {r.text[:200]}")
            if r.status_code != 200:
                # 4xx 는 요청이 잘못된 것이라 재시도해도 같다.
                raise LlmError(f"request rejected {r.status_code}: {r.text[:300]}")

            data = r.json()
            _check_model(data)
            choices = data.get("choices") or []
            if not choices:
                raise LlmError(f"no choices: {str(data)[:200]}")

            text = strip_thinking(choices[0].get("message", {}).get("content") or "")

            finish = choices[0].get("finish_reason")
            if finish == "length":
                # max_tokens 에서 잘렸다. 문장이 중간에 끊겨 있을 수 있다.
                logger.warning("LLM output truncated (max_tokens=%d)", max_tokens)

            return text

        except LlmError as exc:
            last = exc
            if "request rejected" in str(exc):
                raise                       # 재시도 무의미
        except requests.RequestException as exc:
            last = exc

        if attempt < retries:
            # 지수 백오프 + 지터. 서버가 잠깐 바쁠 때 몰려가지 않게.
            wait = min(2 ** attempt, 8) + random.random()
            logger.warning("LLM 호출 실패 (%d/%d): %s — %.1f초 후 재시도",
                           attempt + 1, retries + 1, last, wait)
            time.sleep(wait)

    raise LlmError(f"{retries + 1}회 시도 실패: {last}")
