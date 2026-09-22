from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Iterable


ARTICLE_ISSUE_ASSIGNED = "ARTICLE_ISSUE_ASSIGNED"


class InvalidIssueEmbedding(ValueError):
    """Issue embedding을 유사도 계산에 사용할 수 없을 때 발생한다."""


@dataclass(frozen=True)
class IssueCandidate:

    issue_id: int
    theme_id: int
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class IssueMatch:

    issue_id: int
    similarity: float


def _numeric_embedding(value: Any, field: str) -> tuple[float, ...]:
    # Issue.embedding은 현재 TEXT 컬럼이므로 JDBC에서 문자열로 읽힐 수 있다.
    # JSON 배열 문자열과 이미 배열로 변환된 값 두 형식을 모두 허용한다.
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError as exc:
            raise InvalidIssueEmbedding(f"{field} must be a JSON array") from exc

    if not isinstance(value, (list, tuple)) or not value:
        raise InvalidIssueEmbedding(f"{field} must be a non-empty array")

    if any(
        isinstance(item, bool)
        or not isinstance(item, (int, float))
        or not math.isfinite(float(item))
        for item in value
    ):
        raise InvalidIssueEmbedding(f"{field} must contain only finite numbers")

    return tuple(float(item) for item in value)


def parse_issue_candidate(row: dict[str, Any]) -> IssueCandidate:

    return IssueCandidate(
        issue_id=row["issue_id"],
        theme_id=row["theme_id"],
        embedding=_numeric_embedding(row.get("embedding"), "issue.embedding"),
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

    # 부동소수점 오차로 이론적 범위인 -1~1을 아주 조금 벗어나는 것을 방지한다.
    return max(-1.0, min(1.0, dot_product / (left_norm * right_norm)))


def find_best_issue(
    article_embedding: Iterable[float],
    issues: Iterable[IssueCandidate],
    threshold: float,
) -> IssueMatch | None:

    if not 0.0 <= threshold <= 1.0:
        raise ValueError("issue match threshold must be between 0 and 1")

    best: IssueMatch | None = None
    for issue in issues:
        similarity = cosine_similarity(article_embedding, issue.embedding)
        if similarity is None or similarity < threshold:
            continue

        # 동점이면 작은 issue_id를 선택해 재처리 결과가 항상 같도록 한다.
        if best is None or similarity > best.similarity or (
            similarity == best.similarity and issue.issue_id < best.issue_id
        ):
            best = IssueMatch(issue_id=issue.issue_id, similarity=similarity)

    return best


def build_issue_result(
    article: dict[str, Any],
    issues: Iterable[IssueCandidate],
    threshold: float,
    event_topic: str,
    unclassified_topic: str,
) -> tuple[str, str, str]:

    # 호출 측에서 Theme별로 그룹화하지만 순수 함수에서도 한 번 더 경계를 보장한다.
    same_theme_issues = (
        issue for issue in issues if issue.theme_id == article["theme_id"]
    )
    match = find_best_issue(article["embedding"], same_theme_issues, threshold)
    if match is not None:
        event = {
            "event_type": ARTICLE_ISSUE_ASSIGNED,
            "occurred_at": article["occurred_at"],
            "payload": {
                "article_id": article["article_id"],
                "issue_id": match.issue_id,
                "similarity": match.similarity,
            },
        }
        return (
            event_topic,
            article["article_id"],
            json.dumps(event, ensure_ascii=False, separators=(",", ":")),
        )

    # 매칭되지 않은 기사는 다음 클러스터링 단계가 사용할 최소 정보만 보낸다.
    unclassified = {
        "article_id": article["article_id"],
        "theme_id": article["theme_id"],
        "embedding": list(article["embedding"]),
        "title": article["title"],
        "summary": article.get("summary"),
        "published_at": article["published_at"],
        "unclassified_at": article["occurred_at"],
    }
    return (
        unclassified_topic,
        str(article["theme_id"]),
        json.dumps(unclassified, ensure_ascii=False, separators=(",", ":")),
    )
