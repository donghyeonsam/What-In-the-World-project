"""기사 제목을 본문 문맥을 참고하여 자연스러운 한국어로 번역한다.

이전 버전에서 바뀐 것은 '모델을 어떻게 부르는가' 하나뿐이다.

    이전   Qwen 을 이 프로세스에 직접 로드(약 16GB) → model.generate()
    지금   vLLM 서버에 HTTP 요청

  프롬프트(_build_prompt), 후처리(_clean_translation), 본문 참고량
  (BODY_LEAD_MAX_CHARS), 한국어 기사 건너뛰기, 실패 시 RuntimeError —
  전부 그대로다. 출력 품질을 좌우하는 부분은 손대지 않았다.

왜 프로세스에서 모델을 빼는가
  · 워커 재시작이 몇 초로 줄어든다 (16GB 를 다시 안 올린다)
  · 여러 기사의 요청을 GPU 가 알아서 겹쳐 처리한다 (continuous batching)
  · 모델 교체가 vLLM 서버 재시작 한 번이다

  모델 자체는 서버 쪽에서 정한다. vllm serve --served-model-name 으로 붙인
  이름을 LLM_MODEL 환경변수로 가리킨다(기본 news-llm). 그래서 이 파일은
  어떤 모델이 뒤에 있는지 몰라도 된다.
"""

from __future__ import annotations

import logging

from .llm_client import LlmError, chat

logger = logging.getLogger(__name__)

# 제목 번역의 문맥으로 사용할 본문 최대 문자 수
BODY_LEAD_MAX_CHARS = 1000

# 번역 결과가 제목이므로 과도한 생성을 방지
MAX_NEW_TOKENS = 128


def _build_prompt(title, body_lead, language_code):
    return f"""
다음 해외 뉴스 기사의 제목을 한국어 뉴스 제목으로 번역하세요.

원문 언어: {language_code}

[원문 제목]
{title}

[본문 참고]
{body_lead}

번역 규칙:
1. 본문은 제목의 문맥을 파악하기 위한 참고 자료로만 사용하세요.
2. 제목에 없는 사실을 새롭게 추가하거나 추측하지 마세요.
3. 원문의 시간, 숫자, 인명, 지명, 기관명, 사건 관계를 정확하게 유지하세요.
4. "몇 시간 전", "며칠 후" 등 시간 표현을 임의로 바꾸지 마세요.
5. 직역투를 피하고 자연스러운 한국 언론 제목 형식으로 번역하세요.
6. 원문이 자극적인 표현을 사용하더라도 의미와 뉘앙스를 임의로 삭제하지 마세요.
7. 출력은 반드시 한국어로 작성하세요.
8. 중국어 한자나 일본어 문자를 사용하지 마세요.
9. 고유명사 등 필요한 경우에만 영문 알파벳과 숫자를 사용할 수 있습니다.
10. 설명, 주석, 따옴표 없이 번역된 제목 한 줄만 출력하세요.
""".strip()


def _clean_translation(text):
    """모델 출력에서 불필요한 공백이나 따옴표를 제거한다."""
    if not isinstance(text, str):
        return ""

    text = text.strip()

    # 모델이 가끔 제목 전체를 따옴표로 감싸는 경우 제거
    if len(text) >= 2:
        pairs = (
            ('"', '"'),
            ("'", "'"),
            ("“", "”"),
            ("‘", "’"),
        )

        for left, right in pairs:
            if text.startswith(left) and text.endswith(right):
                text = text[1:-1].strip()
                break

    return text


def translate_title(article, language_code):
    """
    기사 제목을 한국어로 번역한다.

    - 한국어 기사: 원문 제목 그대로 반환
    - 그 외 언어: 제목 + 본문 앞부분을 vLLM 에 전달하여 번역
    """

    title = article["title"].strip()

    # 이미 한국어인 경우 LLM을 호출하지 않는다.
    if language_code == "ko":
        return title

    body = article.get("body") or ""
    body_lead = body.strip()[:BODY_LEAD_MAX_CHARS]

    prompt = _build_prompt(
        title=title,
        body_lead=body_lead,
        language_code=language_code,
    )

    # 이전에는 apply_chat_template(enable_thinking=False) + generate 였다.
    # 지금은 user 메시지 하나로 보내고, 추론 모드 차단은 llm_client 가
    # chat_template_kwargs 로 넘긴다. 모델이 보는 문자열은 같다.
    try:
        raw = chat(
            None,                      # system 메시지 없음 — 이전과 동일한 구성
            prompt,
            max_tokens=MAX_NEW_TOKENS,
            temperature=0.0,
        )
    except LlmError as exc:
        raise RuntimeError(
            f"Title translation failed: "
            f"article_id={article.get('article_id')}: {exc}"
        ) from exc

    translated_title = _clean_translation(raw)

    if not translated_title:
        raise RuntimeError(
            f"Title translation returned empty result: article_id={article.get('article_id')}"
        )

    return translated_title