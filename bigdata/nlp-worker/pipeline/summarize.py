"""기사 본문을 한국어 3문장으로 요약한다.

한국어 기사와 그 외를 한 프롬프트에서 분기한다
  한국어 기사는 번역이 필요 없지만 요약은 필요하다. 그래서 작업 지시문만 바꾸고
  (요약 / 요약+번역) system 과 기사 블록은 그대로 둔다. 그래야 prefix caching 이
  살아 있고, 코드 경로도 하나로 유지된다.

가드레일
  요약은 사용자가 그대로 읽는 텍스트다. 테마가 틀리면 분류가 어긋나는 정도지만
  요약이 이상하면 그게 서비스의 얼굴이 된다. 그래서 모델 출력을 그대로 믿지 않고
  네 가지를 검사한다.

    1. 비어 있거나 너무 짧은가
    2. 한국어인가            (모델이 가끔 원문 언어로 답한다)
    3. 너무 길지 않은가      (3문장 요청인데 문단이 오는 경우)
    4. 머리말·따옴표가 붙었나 ("요약:", "다음은 ...", 전체를 감싼 따옴표)

  1~3 에 걸리면 한 번 더 시도하고, 그래도 안 되면 None 을 돌려준다.
  요약 실패로 기사 자체를 버리지 않는다 — 요약이 없는 기사가 사라진 기사보다 낫다.

언어 판정을 모델 없이 하는 이유
  language.py 의 fastText 를 쓸 수도 있지만, 한글 음절 비율만 봐도 "한국어로
  답했는가"는 충분히 걸러진다. 프롬프트 튜닝용 단독 스크립트에서도 모델 로드 없이
  그대로 쓸 수 있다는 장점이 크다.
"""

from __future__ import annotations

import logging
import re

from .llm_client import LlmError, chat
from .news_prompt import SYSTEM, TASK_SUMMARY_KO, TASK_SUMMARY_TRANSLATE, build_user

logger = logging.getLogger(__name__)

# 3문장 × 60자 = 180자. 여유를 두고 상한을 잡는다.
MAX_SUMMARY_CHARS = 400
MIN_SUMMARY_CHARS = 20
# 3문장 요청이므로 출력 토큰은 넉넉히 300이면 충분하다. 잘리는 것보다는 남기는 편.
MAX_TOKENS = 300

_HANGUL = re.compile(r"[가-힣]")
_LETTERS = re.compile(r"[^\W\d_]", re.UNICODE)
# 모델이 가끔 붙이는 머리말
_LEAD_IN = re.compile(
    r"^\s*(요약|다음은[^\n:]{0,20}|아래는[^\n:]{0,20}|Summary|번역)\s*[:：]\s*",
    re.I,
)
_QUOTE_PAIRS = (('"', '"'), ("'", "'"), ("“", "”"), ("‘", "’"))


def korean_ratio(text: str) -> float:
    """글자 중 한글 음절의 비율. 숫자·기호·공백은 분모에서 뺀다."""
    letters = _LETTERS.findall(text or "")
    if not letters:
        return 0.0
    hangul = _HANGUL.findall(text or "")
    return len(hangul) / len(letters)


def clean(text: str | None) -> str:
    """머리말, 감싼 따옴표, 불릿 기호를 뗀다."""
    t = (text or "").strip()
    if not t:
        return ""

    t = _LEAD_IN.sub("", t).strip()

    for left, right in _QUOTE_PAIRS:
        if len(t) >= 2 and t.startswith(left) and t.endswith(right):
            t = t[1:-1].strip()
            break

    # 줄머리 번호·불릿 제거 후 한 문단으로 합친다
    lines = []
    for line in t.split("\n"):
        line = re.sub(r"^\s*(?:[-*•·]|\d+[.)])\s*", "", line).strip()
        if line:
            lines.append(line)
    return " ".join(lines).strip()


def _problem(text: str) -> str | None:
    """재시도해야 할 이유. 문제없으면 None."""
    if not text:
        return "빈 출력"
    if len(text) < MIN_SUMMARY_CHARS:
        return f"너무 짧음 ({len(text)}자)"
    if len(text) > MAX_SUMMARY_CHARS:
        return f"너무 김 ({len(text)}자)"
    if korean_ratio(text) < 0.3:
        return f"한국어가 아님 (한글 비율 {korean_ratio(text):.0%})"
    return None


def summarize(article: dict, language_code: str | None) -> str | None:
    """기사 요약. 실패하면 None (기사는 그대로 통과시킨다)."""
    title = (article.get("title") or "").strip()
    body = (article.get("body") or "").strip()
    if not (title or body):
        return None

    task = TASK_SUMMARY_KO if language_code == "ko" else TASK_SUMMARY_TRANSLATE
    user = build_user(title, body, language_code, task)

    for attempt, temperature in enumerate((0.0, 0.3)):
        try:
            raw = chat(SYSTEM, user, max_tokens=MAX_TOKENS, temperature=temperature)
        except LlmError as exc:
            logger.warning("요약 호출 실패 article_id=%s: %s",
                           article.get("article_id"), exc)
            return None

        text = clean(raw)
        problem = _problem(text)
        if problem is None:
            return text

        logger.warning("요약 재시도 article_id=%s (%d차): %s | 출력=%r",
                       article.get("article_id"), attempt + 1, problem, text[:120])

    logger.warning("요약 포기 article_id=%s", article.get("article_id"))
    return None
