"""
기사 언어 판별 모듈.

fastText Language Identification 모델을 이용해
기사의 title과 body에서 작성 언어를 판별하고,
2글자 language_code를 반환한다.
"""

from pathlib import Path

import fasttext


# 언어 판별 모델 경로
MODEL_PATH = (
        Path(__file__).resolve().parent.parent
        / "models"
        / "lid.176.bin"
)


# NLP Worker 시작 시 언어 판별 모델을 한 번만 로드한다.
_language_model = fasttext.load_model(str(MODEL_PATH))


# 기사 제목과 본문을 이용해 작성 언어를 판별한다.
def detect_language(article):
    title = article.get("title", "")
    body = article.get("body", "")

    # 제목과 본문을 합쳐 언어 판별에 사용한다.
    text = f"{title}\n{body}".strip()

    # 판별할 텍스트가 없으면 None을 반환한다.
    if not text:
        return None

    # fastText 입력을 한 줄 문자열로 정리한다.
    text = text.replace("\n", " ")

    # 가장 가능성이 높은 언어 1개를 판별한다.
    labels, probabilities = _language_model.predict(
        text,
        k=1,
    )

    # 언어를 판별하지 못한 경우 None을 반환한다.
    if not labels:
        return None

    # "__label__ko" -> "ko"
    language_code = labels[0].replace("__label__", "")

    return language_code