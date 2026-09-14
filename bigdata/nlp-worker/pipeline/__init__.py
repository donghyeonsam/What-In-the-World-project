"""Collector 필드를 보존하면서 실제 NLP 결과를 추가한다."""

import json

from datetime import datetime, timezone

from .language import detect_language
from .country import get_country_code, extract_mentioned_countries
from .embedding import create_article_embedding
from .classifier import classify_theme
from .sentiment import analyze_sentiment
from .title_translation import translate_title


class InvalidArticle(ValueError):
    """재시도로 정상화되지 않는 입력 오류. 모델 오류와 구분한다."""


def validate_article(article):
    if not isinstance(article, dict):
        raise InvalidArticle("article must be a JSON object")

    for key in (
        "article_id",
        "source_name",
        "article_url",
        "title",
        "country",
        "published_at",
        "discovered_at",
    ):
        if not isinstance(article.get(key), str) or not article[key].strip():
            raise InvalidArticle(f"{key} must be a non-empty string")

    if article.get("body") is not None and not isinstance(article["body"], str):
        raise InvalidArticle("body must be a string or null")

    for key in ("published_at", "discovered_at"):
        try:
            parsed = datetime.fromisoformat(
                article[key].strip().replace("Z", "+00:00")
            )
            if parsed.tzinfo is None:
                raise ValueError("timezone required")
        except ValueError as exc:
            raise InvalidArticle(
                f"{key} must be an ISO-8601 timestamp with timezone"
            ) from exc

    try:
        json.dumps(
            article,
            allow_nan=False,
            ensure_ascii=False,
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise InvalidArticle(
            "article must contain finite, UTF-8 JSON values"
        ) from exc

    country_code = get_country_code(article["country"])

    if country_code is None:
        raise InvalidArticle(
            f"Unsupported publishing country: {article['country']}"
        )

    return country_code


def process_article(article):
    country_code = validate_article(article)

    # 1. 언어 감지
    language_code = detect_language(article)

    if not language_code:
        raise RuntimeError(
            "Language model returned no language for a non-empty article"
        )

    # 2. 제목 한국어 번역
    # title_translation.py 내부에서:
    # - 한국어 기사면 원문 title 그대로 반환
    # - 그 외 언어면 title + body 일부를 참고하여 한국어 제목 생성
    translated_title = translate_title(
        article,
        language_code,
    )

    if not isinstance(translated_title, str) or not translated_title.strip():
        raise RuntimeError(
            "Title translation returned no title for a non-empty article"
        )

    translated_title = translated_title.strip()

    # 3. 본문에서 언급된 국가 추출
    mentioned = extract_mentioned_countries(
        article,
        language_code,
    )

    # 4. 기사 임베딩 생성
    embedding = create_article_embedding(article)

    if embedding is None:
        raise RuntimeError(
            "Embedding model returned no vector for a non-empty article"
        )

    # 5. Theme / Field 분류
    theme = classify_theme(embedding)

    # 원본 dict를 덮어쓰지 않아
    # archive/재처리 입력과 collector 필드를 보존한다.
    enriched = dict(article)

    enriched["nlp_worker_data"] = {
        "country_code": country_code,
        "language_code": language_code,

        # 한국어 표시용 제목
        "translated_title": translated_title,

        "field_id": theme["field_id"],
        "theme_id": theme["theme_id"],
        "theme_relevance_score": theme["similarity"],
        "mentioned_countries": mentioned,
        "sentiment": analyze_sentiment(article),
        "article_embedding": embedding,
        "processed_at": datetime.now(timezone.utc).isoformat(),
        "version": "v1",
    }

    return enriched