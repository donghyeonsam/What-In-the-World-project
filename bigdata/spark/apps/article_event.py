"""Pure transformations for the enriched article Spark stream."""

from __future__ import annotations

import json
import math
import re
from typing import Any


EVENT_TYPE = "ARTICLE_UPSERT"
COUNTRY_CODE_PATTERN = re.compile(r"^[A-Z]{2}$")


class InvalidEnrichedArticle(ValueError):
    """Raised when an enriched message does not satisfy the pipeline contract."""


def _required_text(container: dict[str, Any], field: str) -> str:
    # DB 저장에 필수인 문자열 필드가 누락되거나 공백만 들어오는 것을 차단한다.
    value = container.get(field)
    if not isinstance(value, str) or not value.strip():
        raise InvalidEnrichedArticle(f"{field} must be a non-empty string")
    return value.strip()


def _normalize_country_code(value: Any, field: str) -> str:
    # 파이프라인과 DB가 약속한 ISO alpha-2 대문자 형식으로 정규화한다.
    if not isinstance(value, str):
        raise InvalidEnrichedArticle(f"{field} must be a two-letter country code")

    country_code = value.strip().upper()
    if not COUNTRY_CODE_PATTERN.fullmatch(country_code):
        raise InvalidEnrichedArticle(f"{field} must be a two-letter country code")
    return country_code


def _tone_score(sentiment: Any) -> float:
    # NLP의 sentiment.score를 DB의 tone_score로 사용하므로 0~100 범위를 보장한다.
    if not isinstance(sentiment, dict):
        raise InvalidEnrichedArticle("nlp_worker_data.sentiment must be an object")

    value = sentiment.get("score")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidEnrichedArticle(
            "nlp_worker_data.sentiment.score must be a number"
        )

    score = float(value)
    if not math.isfinite(score) or not 0.0 <= score <= 100.0:
        raise InvalidEnrichedArticle(
            "nlp_worker_data.sentiment.score must be between 0 and 100"
        )
    return score


def _theme_relevance_score(value: Any) -> float:
    # NLP ThemeClassifier가 계산한 Top-1 cosine similarity를 그대로 보존한다.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidEnrichedArticle(
            "nlp_worker_data.theme_relevance_score must be a number"
        )

    score = float(value)
    if not math.isfinite(score) or not -1.0 <= score <= 1.0:
        raise InvalidEnrichedArticle(
            "nlp_worker_data.theme_relevance_score must be between -1 and 1"
        )
    return score


def _mentioned_countries(value: Any) -> list[dict[str, Any]]:
    # 기사에 언급된 국가도 발행 국가와 동일한 두 글자 국가 코드 계약을 적용한다.
    if value is None:
        return []
    if not isinstance(value, list):
        raise InvalidEnrichedArticle(
            "nlp_worker_data.mentioned_countries must be an array"
        )

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise InvalidEnrichedArticle(
                f"nlp_worker_data.mentioned_countries[{index}] must be an object"
            )
        count = item.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise InvalidEnrichedArticle(
                f"nlp_worker_data.mentioned_countries[{index}].count "
                "must be a non-negative integer"
            )

        normalized.append(
            {
                "country_code": _normalize_country_code(
                    item.get("country_code"),
                    f"nlp_worker_data.mentioned_countries[{index}].country_code",
                ),
                "count": count,
            }
        )
    return normalized


def build_article_upsert_event(article: dict[str, Any]) -> dict[str, Any]:
    """Validate one enriched article and map it to ARTICLE_UPSERT."""

    # 원본 수집 데이터와 NLP 결과에서 ARTICLE_UPSERT에 필요한 값을 꺼낸다.
    article_id = _required_text(article, "article_id")
    nlp = article.get("nlp_worker_data")
    if not isinstance(nlp, dict):
        raise InvalidEnrichedArticle("nlp_worker_data must be an object")

    theme_id = nlp.get("theme_id")
    if isinstance(theme_id, bool) or not isinstance(theme_id, int):
        raise InvalidEnrichedArticle("nlp_worker_data.theme_id must be an integer")

    embedding = nlp.get("article_embedding")
    if not isinstance(embedding, list) or not embedding:
        raise InvalidEnrichedArticle(
            "nlp_worker_data.article_embedding must be a non-empty array"
        )
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(float(item))
        for item in embedding
    ):
        raise InvalidEnrichedArticle(
            "nlp_worker_data.article_embedding must contain only numbers"
        )

    processed_at = _required_text(nlp, "processed_at")
    discovered_at = _required_text(article, "discovered_at")
    published_at = _required_text(article, "published_at")

    # 현재 단계에서 실제 기사 저장에 필요한 데이터만 이벤트에 포함한다.
    return {
        "event_type": EVENT_TYPE,
        "occurred_at": processed_at,
        "payload": {
            "article_id": article_id,
            "publisher_country_code": _normalize_country_code(
                nlp.get("country_code"), "nlp_worker_data.country_code"
            ),
            "theme_id": theme_id,
            "theme_relevance_score": _theme_relevance_score(
                nlp.get("theme_relevance_score")
            ),
            "publisher": _required_text(article, "source_name"),
            "url": _required_text(article, "article_url"),
            "original_title": _required_text(article, "title"),
            "translated_title": _required_text(
                nlp, "translated_title"
            ),
            "crawled_at": discovered_at,
            "embedding": [float(item) for item in embedding],
            "tone_score": _tone_score(nlp.get("sentiment")),
            "published_at": published_at,
            "mentioned_countries": _mentioned_countries(
                nlp.get("mentioned_countries")
            ),
        },
    }


def transform_kafka_message(raw_value: str) -> tuple[str, str]:
    """Return the Kafka key/value pair for one enriched Kafka value."""

    # Spark Kafka Source가 읽은 문자열을 JSON 객체로 역직렬화한다.
    if not isinstance(raw_value, str):
        raise InvalidEnrichedArticle("value는 무조건 json이어야 합니다.")

    try:
        article = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise InvalidEnrichedArticle("value는 무조건 json이어야 합니다.") from exc

    if not isinstance(article, dict):
        raise InvalidEnrichedArticle("value는 무조건 json이어야 합니다.")

    event = build_article_upsert_event(article)

    # 같은 기사의 이벤트가 가능한 한 같은 Kafka Partition으로 전달되도록
    # article_id를 Kafka Key로 사용한다.
    return event["payload"]["article_id"], json.dumps(
        event, ensure_ascii=False, separators=(",", ":")
    )
