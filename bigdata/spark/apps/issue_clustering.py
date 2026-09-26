"""Pure clustering and event transformations for unclassified articles."""

from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence


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


@dataclass(frozen=True)
class GeneratedIssueDecision:
    issue: GeneratedIssue
    included_article_ids: tuple[str, ...]
    excluded_article_ids: tuple[str, ...]


@dataclass(frozen=True)
class ClusterAttempt:
    """One exact article-membership set already submitted to GMS."""

    lineage_id: str
    theme_id: int
    article_ids: tuple[str, ...]
    attempted_at: str


@dataclass(frozen=True)
class ClusterAttemptDecision:
    should_attempt: bool
    previous: ClusterAttempt | None
    reason: str


@dataclass(frozen=True)
class ClusterAttempt:
    """One exact article-membership set already submitted to GMS."""

    lineage_id: str
    theme_id: int
    article_ids: tuple[str, ...]
    attempted_at: str


@dataclass(frozen=True)
class ClusterAttemptDecision:
    should_attempt: bool
    previous: ClusterAttempt | None
    reason: str


@dataclass(frozen=True)
class ClusterAttempt:
    """One exact article-membership set already submitted to GMS."""

    lineage_id: str
    theme_id: int
    article_ids: tuple[str, ...]
    attempted_at: str


@dataclass(frozen=True)
class ClusterAttemptDecision:
    should_attempt: bool
    previous: ClusterAttempt | None
    reason: str


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


def should_trigger_theme_clustering(
    pending_count: int,
    new_since_last_cluster: int,
    last_clustered_at: str | None,
    *,
    now: datetime | None = None,
    initial_trigger_count: int = 50,
    minimum_pending_count: int = 8,
    immediate_retrigger_count: int = 50,
    delayed_retrigger_count: int = 10,
    delayed_retrigger_minutes: int = 60,
) -> bool:
    """Decide whether one theme is due for another clustering pass.

    A theme is first evaluated after it accumulates the initial threshold. After
    that watermark is recorded, it is evaluated again either after a large
    arrival burst or after a smaller burst has waited long enough.
    """

    counts = (
        pending_count,
        new_since_last_cluster,
        initial_trigger_count,
        minimum_pending_count,
        immediate_retrigger_count,
        delayed_retrigger_count,
        delayed_retrigger_minutes,
    )
    if any(isinstance(value, bool) or not isinstance(value, int) for value in counts):
        raise ValueError("clustering trigger counts must be integers")
    if pending_count < 0 or new_since_last_cluster < 0:
        raise ValueError("article counts must not be negative")
    if (
        initial_trigger_count < 1
        or minimum_pending_count < 1
        or immediate_retrigger_count < 1
        or delayed_retrigger_count < 1
        or delayed_retrigger_minutes < 1
    ):
        raise ValueError("clustering trigger thresholds must be positive")
    if delayed_retrigger_count > immediate_retrigger_count:
        raise ValueError(
            "delayed retrigger count must not exceed immediate retrigger count"
        )

    if last_clustered_at is None:
        return pending_count >= initial_trigger_count
    if pending_count < minimum_pending_count:
        return False

    try:
        last_clustered = datetime.fromisoformat(
            last_clustered_at.replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise ValueError("last_clustered_at must be an ISO-8601 timestamp") from exc
    if last_clustered.tzinfo is None:
        raise ValueError("last_clustered_at must include a timezone")

    evaluated_at = now or datetime.now(timezone.utc)
    if evaluated_at.tzinfo is None:
        raise ValueError("now must include a timezone")
    if new_since_last_cluster >= immediate_retrigger_count:
        return True
    return (
        new_since_last_cluster >= delayed_retrigger_count
        and evaluated_at - last_clustered
        >= timedelta(minutes=delayed_retrigger_minutes)
    )


def decide_cluster_attempt(
    cluster: ClusterCandidate,
    attempts_by_id: Mapping[str, ClusterAttempt],
) -> ClusterAttemptDecision:
    """Block only an exact article-membership set already submitted to GMS."""

    cluster_id = cluster_event_key(cluster)
    previous = attempts_by_id.get(cluster_id)
    article_ids = tuple(sorted(article.article_id for article in cluster.articles))
    if (
        previous is not None
        and previous.theme_id == cluster.theme_id
        and previous.article_ids == article_ids
    ):
        return ClusterAttemptDecision(False, previous, "exact_cluster_already_attempted")
    return ClusterAttemptDecision(True, None, "new_cluster")


def record_cluster_attempt(
    cluster: ClusterCandidate,
    attempted_at: str,
) -> ClusterAttempt:
    """Record an exact cluster after a real semantic GMS attempt."""

    return ClusterAttempt(
        lineage_id=cluster_event_key(cluster),
        theme_id=cluster.theme_id,
        article_ids=tuple(sorted(article.article_id for article in cluster.articles)),
        attempted_at=attempted_at,
    )


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
    min_centroid_similarity: float = -1.0,
) -> tuple[ClusterCandidate, ...]:
    """Run HDBSCAN and return deterministic non-noise cluster candidates."""

    if min_cluster_size < 2:
        raise ValueError("min_cluster_size must be at least 2")
    if representative_count < 1:
        raise ValueError("representative_count must be positive")
    if not 0.0 <= min_membership_confidence <= 1.0:
        raise ValueError("min_membership_confidence must be between 0 and 1")
    if not -1.0 <= min_centroid_similarity <= 1.0:
        raise ValueError("min_centroid_similarity must be between -1 and 1")
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
        cluster_selection_method="leaf",
        # 테마 전체가 하나의 사건으로 강제 수렴하는 것을 막는다. 단일 밀도 군집만
        # 발견된 배치는 더 많은 기사가 들어올 때까지 pending 상태로 유지한다.
        allow_single_cluster=False,
    )
    labels = model.fit_predict([article.embedding for article in articles])
    probabilities = getattr(model, "probabilities_", [1.0] * len(articles))

    clusters: list[ClusterCandidate] = []
    for label in sorted(set(int(value) for value in labels if int(value) >= 0)):
        # 군집 평균이 아니라 기사별 membership probability를 적용한다. 낮은
        # 신뢰도의 경계 기사가 평균에 묻혀 이슈에 포함되는 것을 방지한다.
        member_indices = [
            index
            for index, (article_label, probability) in enumerate(
                zip(labels, probabilities)
            )
            if int(article_label) == label
            and float(probability) >= min_membership_confidence
        ]
        if len(member_indices) < min_cluster_size:
            continue

        # HDBSCAN을 통과했어도 동일 테마라는 이유만으로 가까운 기사를 제거한다.
        # 제거 후 centroid가 이동할 수 있으므로 더 이상 탈락자가 없을 때까지
        # 재계산한다.
        while True:
            centroid = _normalized_centroid(
                [articles[index].embedding for index in member_indices]
            )
            cohesive_indices = [
                index
                for index in member_indices
                if (
                    (
                        similarity := cosine_similarity(
                            articles[index].embedding, centroid
                        )
                    )
                    is not None
                    and similarity >= min_centroid_similarity
                )
            ]
            if len(cohesive_indices) < min_cluster_size:
                member_indices = []
                break
            if cohesive_indices == member_indices:
                break
            member_indices = cohesive_indices

        if not member_indices:
            continue

        members = tuple(articles[index] for index in member_indices)
        member_probabilities = [
            float(probabilities[index]) for index in member_indices
        ]
        membership_confidence = sum(member_probabilities) / len(member_probabilities)

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


def filter_cluster_articles(
    cluster: ClusterCandidate,
    included_article_ids: Iterable[str],
    min_cluster_size: int,
    representative_count: int = 8,
    min_centroid_similarity: float = -1.0,
) -> ClusterCandidate | None:
    """Keep an LLM-approved event subset and rebuild its derived geometry."""

    if min_cluster_size < 2:
        raise ValueError("min_cluster_size must be at least 2")
    if representative_count < 1:
        raise ValueError("representative_count must be positive")
    if not -1.0 <= min_centroid_similarity <= 1.0:
        raise ValueError("min_centroid_similarity must be between -1 and 1")

    included_ids = tuple(included_article_ids)
    included_id_set = set(included_ids)
    if len(included_id_set) != len(included_ids):
        raise ValueError("included_article_ids must not contain duplicates")

    articles_by_id = {article.article_id: article for article in cluster.articles}
    unknown_ids = included_id_set - set(articles_by_id)
    if unknown_ids:
        raise ValueError(
            "included_article_ids contains articles outside the cluster: "
            + ", ".join(sorted(unknown_ids))
        )

    members = tuple(
        article for article in cluster.articles if article.article_id in included_id_set
    )
    if len(members) < min_cluster_size:
        return None

    # LLM 제외 후 중심이 이동하므로 기존과 같은 응집도 경계를 다시 적용한다.
    while True:
        centroid = _normalized_centroid([article.embedding for article in members])
        cohesive_members = tuple(
            article
            for article in members
            if (
                (similarity := cosine_similarity(article.embedding, centroid))
                is not None
                and similarity >= min_centroid_similarity
            )
        )
        if len(cohesive_members) < min_cluster_size:
            return None
        if cohesive_members == members:
            break
        members = cohesive_members

    def representative_key(article: UnclassifiedArticle) -> tuple[float, str]:
        similarity = cosine_similarity(article.embedding, centroid)
        return (-(similarity if similarity is not None else -1.0), article.article_id)

    representatives = tuple(
        sorted(members, key=representative_key)[:representative_count]
    )
    return ClusterCandidate(
        theme_id=cluster.theme_id,
        articles=members,
        centroid=centroid,
        representatives=representatives,
        # HDBSCAN의 기사별 확률은 ClusterCandidate에 보존하지 않으므로 원래
        # 후보 군집의 평균을 유지한다. 이 값은 이벤트 저장에는 사용되지 않는다.
        membership_confidence=cluster.membership_confidence,
    )


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
        merged_issue = GeneratedIssue(name=normalized_name)
        merged.append((merged_cluster, merged_issue))

    return tuple(merged)


def cluster_membership_key(theme_id: int, article_ids: Iterable[str]) -> str:
    """Build a deterministic key for one exact article-membership set."""

    normalized_ids = "\n".join(sorted(article_ids))
    digest = hashlib.sha256(normalized_ids.encode("utf-8")).hexdigest()[:24]
    return f"issue-cluster:{theme_id}:{digest}"


def cluster_event_key(cluster: ClusterCandidate) -> str:
    return cluster_membership_key(
        cluster.theme_id,
        (article.article_id for article in cluster.articles),
    )


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
    article_similarities: dict[str, float] = {}
    for article in sorted(cluster.articles, key=lambda item: item.article_id):
        similarity = cosine_similarity(article.embedding, cluster.centroid)
        if similarity is None:
            raise InvalidUnclassifiedArticle(
                f"article {article.article_id} cannot be compared with cluster centroid"
            )
        article_similarities[article.article_id] = similarity

    event = {
        "event_type": ISSUE_CREATE,
        "occurred_at": occurred_at,
        "payload": {
            "theme_id": cluster.theme_id,
            "name": generated.name,
            "embedding": list(cluster.centroid),
            "article_ids": sorted(article.article_id for article in cluster.articles),
            "article_similarities": article_similarities,
            "first_seen_at": first_seen_at,
        },
    }
    return (
        (
            cluster_event_key(cluster),
            json.dumps(event, ensure_ascii=False, separators=(",", ":")),
        ),
    )
