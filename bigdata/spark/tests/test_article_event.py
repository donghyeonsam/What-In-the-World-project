import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from article_event import (  # noqa: E402
    InvalidEnrichedArticle,
    build_article_upsert_event,
)


class ArticleEventTest(unittest.TestCase):
    def setUp(self):
        self.article = {
            "article_id": "a-123",
            "source_name": "Publisher",
            "article_url": "https://example.com/article",
            "title": "Title",
            "discovered_at": "2026-09-01T08:22:28.256121Z",
            "published_at": "2026-09-01T08:15:03Z",
            "nlp_worker_data": {
                "country_code": "KR",
                "theme_id": 27,
                "theme_relevance_score": 0.8123,
                "article_embedding": [0.031, -0.114],
                "sentiment": {"score": 51.5},
                "mentioned_countries": [{"country_code": "US", "count": 3}],
                "processed_at": "2026-09-04T03:20:15Z",
            },
        }

    def test_article_upsert_contains_theme_relevance_score(self):
        event = build_article_upsert_event(self.article)

        self.assertEqual(event["event_type"], "ARTICLE_UPSERT")
        self.assertEqual(event["payload"]["theme_relevance_score"], 0.8123)

    def test_rejects_missing_theme_relevance_score(self):
        del self.article["nlp_worker_data"]["theme_relevance_score"]

        with self.assertRaisesRegex(
            InvalidEnrichedArticle,
            "theme_relevance_score must be a number",
        ):
            build_article_upsert_event(self.article)

    def test_rejects_theme_relevance_score_outside_cosine_range(self):
        self.article["nlp_worker_data"]["theme_relevance_score"] = 1.01

        with self.assertRaisesRegex(
            InvalidEnrichedArticle,
            "theme_relevance_score must be between -1 and 1",
        ):
            build_article_upsert_event(self.article)


if __name__ == "__main__":
    unittest.main()
