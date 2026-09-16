"""Pure clustering and event transformations for unclassified articles."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Sequence


ISSUE_CREATE = "ISSUE_CREATE"


class InvalidUnclassifiedArticle(ValueError):
    """Raised when a news.unclassified.v1 message violates its contract."""


@dataclass(frozen=True)
class UnclassifiedArticle:
    article_id: str
    theme_id: int
    embedding: tuple[float, ...]
    title: str
    published_at: str
    unclassified_at: str
    summary: str | None = None


@dataclass(frozen=True)
class ClusterCandidate:
    theme_id: int
    articles: tuple[UnclassifiedArticle, ...]
    centroid: tuple[float, ...]
    representatives: tuple[UnclassifiedArticle, ...]
    membership_confidence: float


@dataclass(frozen=True)
class GeneratedIssue:
    name: str
    summary: str


def normalize_issue_name(name: str) -> str:
    """Normalize harmless Unicode and whitespace differences before deduplication."""

    return " ".join(unicodedata.normalize("NFKC", name).split())


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidUnclassifiedArticle(f"{field} must be a non-empty string")
    return value.strip()


def _optional_text(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidUnclassifiedArticle(f"{field} must be a string or null")
    normalized = value.strip()
    return normalized or None


def _required_timestamp(value: Any, field: str) -> str:
    text = _required_text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidUnclassifiedArticle(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise InvalidUnclassifiedArticle(f"{field} must include a timezone")
    return text


def numeric_embedding(value: Any, field: str = "embedding") -> tuple[float, ...]:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise InvalidUnclassifiedArticle(f"{field} must be a JSON array") from exc
    if not isinstance(value, (list, tuple)) or not value:
        raise InvalidUnclassifiedArticle(f"{field} must be a non-empty array")
    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(float(item))
        for item in value
    ):
        raise InvalidUnclassifiedArticle(f"{field} must contain only finite numbers")
    return tuple(float(item) for item in value)


def parse_unclassified_message(raw_value: str) -> UnclassifiedArticle:
    if not isinstance(raw_value, str):
        raise InvalidUnclassifiedArticle("value must be a JSON object")
    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise InvalidUnclassifiedArticle("value must be a JSON object") from exc
    if not isinstance(payload, dict):
        raise InvalidUnclassifiedArticle("value must be a JSON object")

    theme_id = payload.get("theme_id")
    if isinstance(theme_id, bool) or not isinstance(theme_id, int) or theme_id <= 0:
        raise InvalidUnclassifiedArticle("theme_id must be a positive integer")

    return UnclassifiedArticle(
        article_id=_required_text(payload.get("article_id"), "article_id"),
        theme_id=theme_id,
        embedding=numeric_embedding(payload.get("embedding")),
        title=_required_text(payload.get("title"), "title"),
        published_at=_required_timestamp(payload.get("published_at"), "published_at"),
        unclassified_at=_required_timestamp(
            payload.get("unclassified_at"), "unclassified_at"
        ),
        summary=_optional_text(payload.get("summary"), "summary"),
    )


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float | None:
    left_values = tuple(float(item) for item in left)
    right_values = tuple(float(item) for item in right)
    if not left_values or len(left_values) != len(right_values):
        return None
    dot_product = sum(a * b for a, b in zip(left_values, right_values))
    left_norm = math.sqrt(sum(item * item for item in left_values))
    right_norm = math.sqrt(sum(item * item for item in right_values))
    if left_norm == 0.0 or right_norm == 0.0:
        return None
    return max(-1.0, min(1.0, dot_product / (left_norm * right_norm)))


def _normalized_centroid(embeddings: Sequence[tuple[float, ...]]) -> tuple[float, ...]:
    dimensions = {len(embedding) for embedding in embeddings}
    if len(dimensions) != 1:
        raise InvalidUnclassifiedArticle("all embeddings must have equal dimensions")
    centroid = tuple(
        sum(embedding[index] for embedding in embeddings) / len(embeddings)
        for index in range(len(embeddings[0]))
    )
    norm = math.sqrt(sum(value * value for value in centroid))
    if norm == 0.0:
        raise InvalidUnclassifiedArticle("cluster centroid must not be a zero vector")
    return tuple(value / norm for value in centroid)


def cluster_articles(
    articles: Sequence[UnclassifiedArticle],
    min_cluster_size: int,
    min_samples: int | None = None,
    representative_count: int = 8,
    min_membership_confidence: float = 0.0,
) -> tuple[ClusterCandidate, ...]:
    """Run HDBSCAN and return deterministic non-noise cluster candidates."""

    if min_cluster_size < 2:
        raise ValueError("min_cluster_size must be at least 2")
    if representative_count < 1:
        raise ValueError("representative_count must be positive")
    if not 0.0 <= min_membership_confidence <= 1.0:
        raise ValueError("min_membership_confidence must be between 0 and 1")
    if len(articles) < min_cluster_size:
        return ()
    theme_ids = {article.theme_id for article in articles}
    if len(theme_ids) != 1:
        raise ValueError("articles from different themes cannot be clustered together")
    dimensions = {len(article.embedding) for article in articles}
    if len(dimensions) != 1:
        raise InvalidUnclassifiedArticle("all embeddings must have equal dimensions")

    # Imported lazily so contract/event unit tests do not require the ML runtime.
    from sklearn.cluster import HDBSCAN

    model = HDBSCAN(
        min_cluster_size=min_cluster_size,
        min_samples=min_samples,
        metric="euclidean",
        cluster_selection_method="eom",
        # A theme batch can legitimately contain one newly emerging issue.
        allow_single_cluster=True,
    )
    labels = model.fit_predict([article.embedding for article in articles])
    probabilities = getattr(model, "probabilities_", [1.0] * len(articles))

    clusters: list[ClusterCandidate] = []
    for label in sorted(set(int(value) for value in labels if int(value) >= 0)):
        members = tuple(
            article
            for article, article_label in zip(articles, labels)
            if int(article_label) == label
        )
        member_probabilities = [
            float(probability)
            for probability, article_label in zip(probabilities, labels)
            if int(article_label) == label
        ]
        membership_confidence = sum(member_probabilities) / len(member_probabilities)
        if membership_confidence < min_membership_confidence:
            continue

        centroid = _normalized_centroid([article.embedding for article in members])

        def representative_key(article: UnclassifiedArticle) -> tuple[float, str]:
            similarity = cosine_similarity(article.embedding, centroid)
            return (-(similarity if similarity is not None else -1.0), article.article_id)

        representatives = tuple(
            sorted(
                members,
                key=representative_key,
            )[:representative_count]
        )
        clusters.append(
            ClusterCandidate(
                theme_id=members[0].theme_id,
                articles=members,
                centroid=centroid,
                representatives=representatives,
                membership_confidence=membership_confidence,
            )
        )

    # HDBSCAN label values themselves are not a durable ordering contract.
    return tuple(sorted(clusters, key=lambda item: item.articles[0].article_id))


def merge_generated_issue_candidates(
    candidates: Sequence[tuple[ClusterCandidate, GeneratedIssue]],
    representative_count: int = 8,
) -> tuple[tuple[ClusterCandidate, GeneratedIssue], ...]:
    """Merge candidates with the same theme and generated issue name."""

    if representative_count < 1:
        raise ValueError("representative_count must be positive")

    grouped: dict[
        tuple[int, str], list[tuple[ClusterCandidate, GeneratedIssue]]
    ] = {}
    for cluster, generated in candidates:
        normalized_name = normalize_issue_name(generated.name)
        if not normalized_name:
            raise ValueError("generated issue name must not be blank")
        grouped.setdefault((cluster.theme_id, normalized_name), []).append(
            (cluster, generated)
        )

    merged: list[tuple[ClusterCandidate, GeneratedIssue]] = []
    for (theme_id, normalized_name), group in sorted(grouped.items()):
        articles_by_id: dict[str, UnclassifiedArticle] = {}
        confidence_total = 0.0
        confidence_weight = 0
        for cluster, _ in group:
            for article in cluster.articles:
                articles_by_id.setdefault(article.article_id, article)
            confidence_total += cluster.membership_confidence * len(cluster.articles)
            confidence_weight += len(cluster.articles)

        articles = tuple(articles_by_id[key] for key in sorted(articles_by_id))
        centroid = _normalized_centroid([article.embedding for article in articles])

        def representative_key(article: UnclassifiedArticle) -> tuple[float, str]:
            similarity = cosine_similarity(article.embedding, centroid)
            return (-(similarity if similarity is not None else -1.0), article.article_id)

        representatives = tuple(
            sorted(articles, key=representative_key)[:representative_count]
        )
        merged_cluster = ClusterCandidate(
            theme_id=theme_id,
            articles=articles,
            centroid=centroid,
            representatives=representatives,
            membership_confidence=confidence_total / confidence_weight,
        )
        merged_issue = GeneratedIssue(
            name=normalized_name,
            summary=group[0][1].summary,
        )
        merged.append((merged_cluster, merged_issue))

    return tuple(merged)


def cluster_event_key(cluster: ClusterCandidate) -> str:
    article_ids = "\n".join(sorted(article.article_id for article in cluster.articles))
    digest = hashlib.sha256(article_ids.encode("utf-8")).hexdigest()[:24]
    return f"issue-cluster:{cluster.theme_id}:{digest}"


def build_issue_events(
    cluster: ClusterCandidate,
    generated: GeneratedIssue,
    occurred_at: str | None = None,
) -> tuple[tuple[str, str], ...]:
    """Build the existing ISSUE_CREATE Kafka key/value contract."""

    occurred_at = occurred_at or datetime.now(timezone.utc).isoformat()
    first_seen_at = min(
        cluster.articles,
        key=lambda article: datetime.fromisoformat(
            article.published_at.replace("Z", "+00:00")
        ),
    ).published_at
    event = {
        "event_type": ISSUE_CREATE,
        "occurred_at": occurred_at,
        "payload": {
            "theme_id": cluster.theme_id,
            "name": generated.name,
            "embedding": list(cluster.centroid),
            "article_ids": sorted(article.article_id for article in cluster.articles),
            "first_seen_at": first_seen_at,
        },
    }
    return (
        (
            cluster_event_key(cluster),
            json.dumps(event, ensure_ascii=False, separators=(",", ":")),
        ),
    )
