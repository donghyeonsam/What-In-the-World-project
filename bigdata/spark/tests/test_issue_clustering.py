import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from issue_clustering import (  # noqa: E402
    ISSUE_CREATE,
    ClusterCandidate,
    GeneratedIssue,
    InvalidUnclassifiedArticle,
    UnclassifiedArticle,
    build_issue_events,
    cluster_articles,
    cluster_event_key,
    parse_unclassified_message,
)


def article(article_id: str, embedding=(1.0, 0.0), published_at="2026-09-03T03:35:24Z"):
    return UnclassifiedArticle(
        article_id=article_id,
        theme_id=12,
        embedding=embedding,
        title=f"title {article_id}",
        published_at=published_at,
        unclassified_at="2026-09-03T04:10:01Z",
    )


class UnclassifiedContractTest(unittest.TestCase):
    def test_parse_valid_message(self):
        parsed = parse_unclassified_message(
            json.dumps(
                {
                    "article_id": "a-123",
                    "theme_id": 12,
                    "embedding": [0.1, 0.2],
                    "title": "미국 반도체 규제 확대",
                    "published_at": "2026-09-03T03:35:24Z",
                    "unclassified_at": "2026-09-03T04:10:01+00:00",
                }
            )
        )
        self.assertEqual(parsed.article_id, "a-123")
        self.assertEqual(parsed.embedding, (0.1, 0.2))

    def test_rejects_timestamp_without_timezone(self):
        with self.assertRaisesRegex(InvalidUnclassifiedArticle, "timezone"):
            parse_unclassified_message(
                json.dumps(
                    {
                        "article_id": "a-123",
                        "theme_id": 12,
                        "embedding": [0.1, 0.2],
                        "title": "title",
                        "published_at": "2026-09-03T03:35:24",
                        "unclassified_at": "2026-09-03T04:10:01Z",
                    }
                )
            )


class IssueEventTest(unittest.TestCase):
    def setUp(self):
        self.cluster = ClusterCandidate(
            theme_id=12,
            articles=(
                article("a-2", published_at="2026-09-03T05:00:00+09:00"),
                article("a-1", published_at="2026-09-02T21:00:00Z"),
            ),
            centroid=(1.0, 0.0),
            representatives=(article("a-1"),),
            membership_confidence=0.95,
        )

    def test_new_issue_event_is_deterministic_and_attaches_all_articles(self):
        generated = GeneratedIssue(
            name="미국의 대중국 반도체 규제 확대",
            summary="요약",
        )
        key, raw_event = build_issue_events(
            self.cluster, generated, "2026-09-03T06:50:00Z"
        )[0]
        event = json.loads(raw_event)

        self.assertEqual(event["event_type"], ISSUE_CREATE)
        self.assertEqual(event["payload"]["article_ids"], ["a-1", "a-2"])
        self.assertEqual(
            event["payload"]["first_seen_at"], "2026-09-03T05:00:00+09:00"
        )
        self.assertEqual(key, cluster_event_key(self.cluster))


class HdbscanTransformationTest(unittest.TestCase):
    def test_discards_noise_and_selects_centroid_representatives(self):
        class FakeHdbscan:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def fit_predict(self, embeddings):
                self.probabilities_ = [0.9, 0.8, 0.2, 0.95, 0.9]
                return [0, 0, -1, 1, 1]

        sklearn_module = types.ModuleType("sklearn")
        cluster_module = types.ModuleType("sklearn.cluster")
        cluster_module.HDBSCAN = FakeHdbscan
        sklearn_module.cluster = cluster_module

        articles = (
            article("a-1", (1.0, 0.0)),
            article("a-2", (0.99, 0.01)),
            article("noise", (0.0, 1.0)),
            article("b-1", (-1.0, 0.0)),
            article("b-2", (-0.99, -0.01)),
        )
        with patch.dict(
            sys.modules,
            {"sklearn": sklearn_module, "sklearn.cluster": cluster_module},
        ):
            clusters = cluster_articles(
                articles,
                min_cluster_size=2,
                min_samples=1,
                representative_count=1,
                min_membership_confidence=0.5,
            )

        self.assertEqual(len(clusters), 2)
        self.assertEqual(
            {item.article_id for cluster in clusters for item in cluster.articles},
            {"a-1", "a-2", "b-1", "b-2"},
        )
        self.assertTrue(all(len(cluster.representatives) == 1 for cluster in clusters))


if __name__ == "__main__":
    unittest.main()
