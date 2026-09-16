import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from issue_matching import build_issue_result  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
