"""본문 요약 프롬프트.

제목 번역은 여기 없다
  title_translation.py 가 자기 프롬프트를 그대로 들고 있다. 잘 돌아가던 기능이라
  문구를 건드리지 않고 모델 호출 방식만 바꿨다. 두 작업의 프롬프트를 합치면
  prefix caching 이득이 있지만(하루 약 6%), 그 대가로 제목 출력이 바뀐다.
  여유가 5배 있는 상황에서 치를 값이 아니라고 봤다.

프롬프트 순서 — vLLM prefix caching
    system : 공통 규칙        모든 기사에 동일  → 기사마다 재계산 안 함
    user   : [기사]
             [작업 지시]

  prefix caching 은 '앞에서부터 같은 부분'만 재사용한다. 그래서 고정 규칙을
  system(맨 앞)에 둔다. 규칙을 프롬프트 끝에 두면 캐시가 전혀 안 걸린다.
"""

from __future__ import annotations

import re

# 본문 상한. prefill 비용이 여기에 비례하므로 가장 큰 조절 레버다.
# 6000자면 한국어 기준 약 3000~4000토큰. 뉴스 기사 대부분이 이 안에 들어간다.
# 처리 시간을 줄여야 하면 여기부터 내린다.
SUMMARY_BODY_CHARS = 6000
MAX_BODY_CHARS = SUMMARY_BODY_CHARS      # 이전 이름 호환
# 제목 뒤에 붙는 매체명을 떼기 위한 최소 길이 보호
_TITLE_TAIL = re.compile(r"\s*[\|｜]\s*[^\|｜]{1,40}\s*$")


# =====================================================================
# system — 모든 호출에 '글자 하나까지' 동일해야 한다. 여기를 바꾸면 캐시가 깨진다.
# =====================================================================
SYSTEM = """\
당신은 해외 뉴스를 한국 독자에게 요약해 전달하는 편집자입니다.

공통 규칙
1. 출력은 반드시 한국어로 작성하세요.
2. 원문에 없는 사실을 추가하거나 추측하지 마세요.
3. 시간, 숫자, 인명, 지명, 기관명, 사건 관계를 원문 그대로 유지하세요.
4. "몇 시간 전", "며칠 후" 같은 시간 표현을 임의로 바꾸지 마세요.
5. 원문이 자극적이더라도 의미와 뉘앙스를 임의로 덜어내지 마세요.
6. 직역투를 피하고 한국 언론 문장으로 자연스럽게 쓰세요.
7. 중국어 한자나 일본어 문자를 쓰지 마세요.
8. 고유명사 등 필요한 경우에만 영문 알파벳과 숫자를 쓸 수 있습니다.
9. 설명, 주석, 머리말, 따옴표 없이 요청한 내용만 출력하세요."""


# =====================================================================
# 작업별 지시 — user 메시지의 '맨 뒤'에 붙는다
# =====================================================================
TASK_SUMMARY_KO = """\
[작업]
위 기사를 3문장으로 요약하세요.

- 정확히 3문장입니다.
- 각 문장은 60자를 넘기지 마세요.
- 기사에 실제로 쓰인 사실만 담으세요. 배경 설명, 전망, 평가는 넣지 마세요.
- 첫 문장에 무슨 일이 일어났는지를 담으세요.
- 번호나 기호 없이 3문장을 이어서 쓰세요."""

TASK_SUMMARY_TRANSLATE = """\
[작업]
위 기사를 읽고 한국어 3문장으로 요약하세요.

- 정확히 3문장입니다.
- 각 문장은 60자를 넘기지 마세요.
- 기사에 실제로 쓰인 사실만 담으세요. 배경 설명, 전망, 평가는 넣지 마세요.
- 첫 문장에 무슨 일이 일어났는지를 담으세요.
- 번호나 기호 없이 3문장을 이어서 쓰세요."""

def clip_body(body: str | None, limit: int = SUMMARY_BODY_CHARS) -> str:
    """본문을 상한까지 자른다. 문장 중간에서 끊기지 않게 조금 물러난다."""
    text = (body or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # 마지막 문장 끝에서 자른다. 너무 많이 물러나면 그냥 상한에서 자른다.
    for mark in ("\n", ". ", "。", "! ", "? ", "！", "？"):
        idx = cut.rfind(mark)
        if idx > limit * 0.7:
            return cut[:idx + len(mark)].strip()
    return cut.strip()


def strip_title_tail(title: str | None) -> str:
    """제목 끝의 매체명을 뗀다. 예: '... | 岩手日報ONLINE'"""
    t = (title or "").strip()
    if not t:
        return ""
    stripped = _TITLE_TAIL.sub("", t).strip()
    # 떼고 나서 너무 짧아지면 제목 본문에 구분자가 있던 것이다. 원본을 쓴다.
    return stripped if len(stripped) >= max(8, len(t) // 3) else t


def build_article_block(title: str | None, body: str | None,
                        language_code: str | None,
                        body_chars: int = SUMMARY_BODY_CHARS) -> str:
    """user 메시지의 앞부분.

    body_chars 가 같으면 두 작업의 이 부분이 완전히 같아져서 prefix caching 이
    걸린다. 다르게 주면 캐시는 못 쓰지만 작업에 맞는 분량을 줄 수 있다.
    """
    return (
        f"[원문 언어]\n{language_code or 'unknown'}\n\n"
        f"[제목]\n{strip_title_tail(title)}\n\n"
        f"[본문]\n{clip_body(body, body_chars)}"
    )


def build_user(title: str | None, body: str | None,
               language_code: str | None, task: str,
               body_chars: int = SUMMARY_BODY_CHARS) -> str:
    return (f"{build_article_block(title, body, language_code, body_chars)}"
            f"\n\n{task}")
