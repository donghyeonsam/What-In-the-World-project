import json
import sys
import types
import unittest
from datetime import datetime, timezone
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
    decide_cluster_attempt,
    filter_cluster_articles,
    merge_generated_issue_candidates,
    parse_unclassified_message,
    record_cluster_attempt,
    should_trigger_theme_clustering,
)


def article(
    article_id: str,
    embedding=(1.0, 0.0),
    published_at="2026-09-03T03:35:24Z",
    theme_id=12,
):
    return UnclassifiedArticle(
        article_id=article_id,
        theme_id=theme_id,
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
                    "summary": "미국 정부가 중국 대상 수출 규제를 확대했다.",
                    "published_at": "2026-09-03T03:35:24Z",
                    "unclassified_at": "2026-09-03T04:10:01+00:00",
                }
            )
        )
        self.assertEqual(parsed.article_id, "a-123")
        self.assertEqual(parsed.embedding, (0.1, 0.2))
        self.assertEqual(
            parsed.summary,
            "미국 정부가 중국 대상 수출 규제를 확대했다.",
        )

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
                article(
                    "a-2",
                    embedding=(0.8, 0.6),
                    published_at="2026-09-03T05:00:00+09:00",
                ),
                article("a-1", published_at="2026-09-02T21:00:00Z"),
            ),
            centroid=(1.0, 0.0),
            representatives=(article("a-1"),),
            membership_confidence=0.95,
        )

    def test_new_issue_event_is_deterministic_and_attaches_all_articles(self):
        generated = GeneratedIssue(name="미국의 대중국 반도체 규제 확대")
        key, raw_event = build_issue_events(
            self.cluster, generated, "2026-09-03T06:50:00Z"
        )[0]
        event = json.loads(raw_event)

        self.assertEqual(event["event_type"], ISSUE_CREATE)
        self.assertEqual(event["payload"]["article_ids"], ["a-1", "a-2"])
        self.assertEqual(
            event["payload"]["article_similarities"],
            {"a-1": 1.0, "a-2": 0.8},
        )
        self.assertEqual(
            event["payload"]["first_seen_at"], "2026-09-03T05:00:00+09:00"
        )
        self.assertEqual(key, cluster_event_key(self.cluster))

    def test_merges_same_theme_and_normalized_name_before_event_creation(self):
        first = ClusterCandidate(
            theme_id=12,
            articles=(article("a-1", (1.0, 0.0)),),
            centroid=(1.0, 0.0),
            representatives=(article("a-1"),),
            membership_confidence=0.9,
        )
        second = ClusterCandidate(
            theme_id=12,
            articles=(article("a-2", (0.0, 1.0)),),
            centroid=(0.0, 1.0),
            representatives=(article("a-2", (0.0, 1.0)),),
            membership_confidence=0.8,
        )

        merged = merge_generated_issue_candidates(
            (
                (first, GeneratedIssue("부동산  시장 동향")),
                (second, GeneratedIssue("부동산 시장 동향")),
            )
        )

        self.assertEqual(len(merged), 1)
        cluster, generated = merged[0]
        self.assertEqual(generated.name, "부동산 시장 동향")
        self.assertEqual([item.article_id for item in cluster.articles], ["a-1", "a-2"])
        self.assertAlmostEqual(cluster.centroid[0], 2 ** -0.5)
        self.assertAlmostEqual(cluster.centroid[1], 2 ** -0.5)

    def test_does_not_merge_same_name_from_different_themes(self):
        first = ClusterCandidate(
            theme_id=12,
            articles=(article("a-1", theme_id=12),),
            centroid=(1.0, 0.0),
            representatives=(article("a-1", theme_id=12),),
            membership_confidence=0.9,
        )
        second = ClusterCandidate(
            theme_id=13,
            articles=(article("a-2", theme_id=13),),
            centroid=(1.0, 0.0),
            representatives=(article("a-2", theme_id=13),),
            membership_confidence=0.9,
        )

        merged = merge_generated_issue_candidates(
            (
                (first, GeneratedIssue("같은 이름")),
                (second, GeneratedIssue("같은 이름")),
            )
        )

        self.assertEqual(len(merged), 2)

    def test_filters_llm_exclusions_and_rebuilds_cluster_geometry(self):
        candidate = ClusterCandidate(
            theme_id=12,
            articles=(
                article("a-1", (1.0, 0.0)),
                article("a-2", (0.8, 0.6)),
                article("different-event", (0.0, 1.0)),
            ),
            centroid=(2 ** -0.5, 2 ** -0.5),
            representatives=(article("different-event", (0.0, 1.0)),),
            membership_confidence=0.91,
        )

        filtered = filter_cluster_articles(
            candidate,
            ("a-1", "a-2"),
            min_cluster_size=2,
            representative_count=1,
            min_centroid_similarity=0.9,
        )

        self.assertIsNotNone(filtered)
        self.assertEqual(
            [item.article_id for item in filtered.articles],
            ["a-1", "a-2"],
        )
        self.assertNotEqual(filtered.centroid, candidate.centroid)
        self.assertEqual(len(filtered.representatives), 1)
        self.assertNotEqual(
            filtered.representatives[0].article_id,
            "different-event",
        )

    def test_discards_llm_subset_below_minimum_cluster_size(self):
        candidate = ClusterCandidate(
            theme_id=12,
            articles=(article("a-1"), article("a-2"), article("a-3")),
            centroid=(1.0, 0.0),
            representatives=(article("a-1"),),
            membership_confidence=0.91,
        )

        filtered = filter_cluster_articles(
            candidate,
            ("a-1",),
            min_cluster_size=2,
        )

        self.assertIsNone(filtered)

    def test_reapplies_centroid_boundary_after_llm_filtering(self):
        candidate = ClusterCandidate(
            theme_id=12,
            articles=(
                article("a-1", (1.0, 0.0)),
                article("a-2", (0.0, 1.0)),
            ),
            centroid=(2 ** -0.5, 2 ** -0.5),
            representatives=(article("a-1"),),
            membership_confidence=0.91,
        )

        filtered = filter_cluster_articles(
            candidate,
            ("a-1", "a-2"),
            min_cluster_size=2,
            min_centroid_similarity=0.92,
        )

        self.assertIsNone(filtered)


class ClusterAttemptPolicyTest(unittest.TestCase):
    @staticmethod
    def _cluster(*article_ids, centroid=(1.0, 0.0)):
        articles = tuple(article(article_id, centroid) for article_id in article_ids)
        return ClusterCandidate(
            theme_id=12,
            articles=articles,
            centroid=centroid,
            representatives=articles[:1],
            membership_confidence=0.95,
        )

    @staticmethod
    def _attempts(*attempts):
        return {attempt.lineage_id: attempt for attempt in attempts}

    def test_new_cluster_is_attempted(self):
        decision = decide_cluster_attempt(
            self._cluster("a", "b", "c", "d"), {}
        )

        self.assertTrue(decision.should_attempt)
        self.assertEqual(decision.reason, "new_cluster")

    def test_exact_article_set_is_skipped_regardless_of_order(self):
        original = self._cluster("a", "b", "c", "d")
        attempt = record_cluster_attempt(
            original, "2026-09-03T04:00:00+00:00"
        )

        decision = decide_cluster_attempt(
            self._cluster("d", "c", "b", "a"),
            self._attempts(attempt),
        )

        self.assertFalse(decision.should_attempt)
        self.assertEqual(decision.reason, "exact_cluster_already_attempted")

    def test_one_changed_article_is_a_new_cluster(self):
        attempt = record_cluster_attempt(
            self._cluster("a", "b", "c", "d"),
            "2026-09-03T04:00:00+00:00",
        )

        decision = decide_cluster_attempt(
            self._cluster("a", "b", "c", "e"),
            self._attempts(attempt),
        )

        self.assertTrue(decision.should_attempt)
        self.assertEqual(decision.reason, "new_cluster")

    def test_centroid_is_ignored_when_article_set_is_exact(self):
        attempt = record_cluster_attempt(
            self._cluster("a", "b", "c", "d", centroid=(1.0, 0.0)),
            "2026-09-03T04:00:00+00:00",
        )

        decision = decide_cluster_attempt(
            self._cluster("a", "b", "c", "d", centroid=(0.0, 1.0)),
            self._attempts(attempt),
        )

        self.assertFalse(decision.should_attempt)

    def test_record_uses_deterministic_exact_cluster_id(self):
        first = record_cluster_attempt(
            self._cluster("a", "b", "c", "d"),
            "2026-09-03T04:00:00+00:00",
        )
        second = record_cluster_attempt(
            self._cluster("d", "c", "b", "a"),
            "2026-09-03T05:00:00+00:00",
        )

        self.assertEqual(first.lineage_id, second.lineage_id)
        self.assertEqual(first.article_ids, ("a", "b", "c", "d"))


class ThemeClusteringTriggerTest(unittest.TestCase):
    NOW = datetime(2026, 9, 25, 15, 0, tzinfo=timezone.utc)

    def test_first_run_requires_fifty_pending_articles(self):
        self.assertFalse(
            should_trigger_theme_clustering(49, 0, None, now=self.NOW)
        )
        self.assertTrue(
            should_trigger_theme_clustering(50, 0, None, now=self.NOW)
        )

    def test_retriggers_immediately_after_fifty_new_articles(self):
        self.assertTrue(
            should_trigger_theme_clustering(
                50,
                50,
                "2026-09-25T14:59:00+00:00",
                now=self.NOW,
            )
        )

    def test_retriggers_after_ten_new_articles_and_sixty_minutes(self):
        self.assertTrue(
            should_trigger_theme_clustering(
                10,
                10,
                "2026-09-25T14:00:00Z",
                now=self.NOW,
            )
        )

    def test_does_not_retrigger_before_delayed_thresholds_are_both_met(self):
        self.assertFalse(
            should_trigger_theme_clustering(
                49,
                9,
                "2026-09-25T13:00:00+00:00",
                now=self.NOW,
            )
        )
        self.assertFalse(
            should_trigger_theme_clustering(
                49,
                10,
                "2026-09-25T14:00:01+00:00",
                now=self.NOW,
            )
        )

    def test_does_not_retrigger_without_enough_current_pending_articles(self):
        self.assertFalse(
            should_trigger_theme_clustering(
                7,
                50,
                "2026-09-25T13:00:00+00:00",
                now=self.NOW,
            )
        )


class HdbscanTransformationTest(unittest.TestCase):
    def test_disables_forced_single_cluster(self):
        class FakeHdbscan:
            kwargs = None

            def __init__(self, **kwargs):
                FakeHdbscan.kwargs = kwargs

            def fit_predict(self, embeddings):
                self.probabilities_ = [1.0] * len(embeddings)
                return [0] * len(embeddings)

        sklearn_module = types.ModuleType("sklearn")
        cluster_module = types.ModuleType("sklearn.cluster")
        cluster_module.HDBSCAN = FakeHdbscan
        sklearn_module.cluster = cluster_module

        with patch.dict(
            sys.modules,
            {"sklearn": sklearn_module, "sklearn.cluster": cluster_module},
        ):
            cluster_articles(
                (article("a-1"), article("a-2")),
                min_cluster_size=2,
                min_samples=1,
            )

        self.assertFalse(FakeHdbscan.kwargs["allow_single_cluster"])

    def test_filters_each_member_by_membership_probability(self):
        class FakeHdbscan:
            def __init__(self, **kwargs):
                pass

            def fit_predict(self, embeddings):
                self.probabilities_ = [1.0, 0.9, 0.2]
                return [0, 0, 0]

        sklearn_module = types.ModuleType("sklearn")
        cluster_module = types.ModuleType("sklearn.cluster")
        cluster_module.HDBSCAN = FakeHdbscan
        sklearn_module.cluster = cluster_module

        articles = (
            article("a-1", (1.0, 0.0)),
            article("a-2", (0.99, 0.01)),
            article("low-confidence", (0.98, 0.02)),
        )
        with patch.dict(
            sys.modules,
            {"sklearn": sklearn_module, "sklearn.cluster": cluster_module},
        ):
            clusters = cluster_articles(
                articles,
                min_cluster_size=2,
                min_samples=1,
                min_membership_confidence=0.7,
            )

        self.assertEqual(len(clusters), 1)
        self.assertEqual(
            [item.article_id for item in clusters[0].articles],
            ["a-1", "a-2"],
        )
        self.assertAlmostEqual(clusters[0].membership_confidence, 0.95)

    def test_filters_members_outside_centroid_similarity_boundary(self):
        class FakeHdbscan:
            def __init__(self, **kwargs):
                pass

            def fit_predict(self, embeddings):
                self.probabilities_ = [1.0, 1.0, 1.0]
                return [0, 0, 0]

        sklearn_module = types.ModuleType("sklearn")
        cluster_module = types.ModuleType("sklearn.cluster")
        cluster_module.HDBSCAN = FakeHdbscan
        sklearn_module.cluster = cluster_module

        articles = (
            article("a-1", (1.0, 0.0)),
            article("a-2", (0.99, 0.01)),
            article("off-topic", (0.0, 1.0)),
        )
        with patch.dict(
            sys.modules,
            {"sklearn": sklearn_module, "sklearn.cluster": cluster_module},
        ):
            clusters = cluster_articles(
                articles,
                min_cluster_size=2,
                min_samples=1,
                min_centroid_similarity=0.8,
            )

        self.assertEqual(len(clusters), 1)
        self.assertEqual(
            [item.article_id for item in clusters[0].articles],
            ["a-1", "a-2"],
        )

    def test_selects_eight_representatives_by_default(self):
        class FakeHdbscan:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def fit_predict(self, embeddings):
                self.probabilities_ = [1.0] * len(embeddings)
                return [0] * len(embeddings)

        sklearn_module = types.ModuleType("sklearn")
        cluster_module = types.ModuleType("sklearn.cluster")
        cluster_module.HDBSCAN = FakeHdbscan
        sklearn_module.cluster = cluster_module

        articles = tuple(
            article(f"a-{index:02d}", (1.0, index / 100.0))
            for index in range(10)
        )
        with patch.dict(
            sys.modules,
            {"sklearn": sklearn_module, "sklearn.cluster": cluster_module},
        ):
            clusters = cluster_articles(
                articles,
                min_cluster_size=2,
                min_samples=1,
            )

        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0].representatives), 8)

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
