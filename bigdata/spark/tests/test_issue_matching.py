import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from issue_matching import IssueCandidate, build_issue_result  # noqa: E402


class IssueMatchingTest(unittest.TestCase):
    def test_unmatched_article_keeps_translated_title_and_summary(self):
        article = {
            "article_id": "a-123",
            "theme_id": 12,
            "embedding": (1.0, 0.0),
            "title": "미국 대중국 반도체 수출 규제 확대",
            "summary": "미국 정부가 중국 대상 수출 규제를 확대했다.",
            "published_at": "2026-09-03T03:35:24Z",
            "occurred_at": "2026-09-03T04:10:01Z",
        }

        topic, key, raw_value = build_issue_result(
            article,
            issues=(),
            threshold=0.85,
            event_topic="news.event.v1",
            unclassified_topic="news.unclassified.v1",
        )
        payload = json.loads(raw_value)

        self.assertEqual(topic, "news.unclassified.v1")
        self.assertEqual(key, "12")
        self.assertEqual(payload["title"], article["title"])
        self.assertEqual(payload["summary"], article["summary"])
        self.assertEqual(payload["embedding"], [1.0, 0.0])

    def test_matches_existing_issue_with_selected_summary_embedding(self):
        article = {
            "article_id": "a-123",
            "theme_id": 12,
            # enriched_article_stream maps the preferred summary_embedding here.
            "embedding": (0.0, 1.0),
            "title": "title",
            "summary": None,
            "published_at": "2026-09-03T03:35:24Z",
            "occurred_at": "2026-09-03T04:10:01Z",
        }
        issues = (
            IssueCandidate(issue_id=1, theme_id=12, embedding=(1.0, 0.0)),
            IssueCandidate(issue_id=2, theme_id=12, embedding=(0.0, 1.0)),
        )

        topic, key, raw_value = build_issue_result(
            article,
            issues=issues,
            threshold=0.9,
            event_topic="news.event.v1",
            unclassified_topic="news.unclassified.v1",
        )
        event = json.loads(raw_value)

        self.assertEqual(topic, "news.event.v1")
        self.assertEqual(key, "a-123")
        self.assertEqual(event["payload"]["issue_id"], 2)


if __name__ == "__main__":
    unittest.main()
