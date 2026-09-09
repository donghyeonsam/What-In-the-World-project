import json
import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from gms_issue_generator import (  # noqa: E402
    GmsConfig,
    GmsIssueGenerationError,
    _completion_url,
    _extract_json_object,
    _request_body,
    validate_generated_issue,
)
from issue_clustering import ClusterCandidate, UnclassifiedArticle  # noqa: E402


class GmsIssueGeneratorTest(unittest.TestCase):
    def setUp(self):
        self.valid = {
            "name": "새 반도체 규제",
            "summary": "미국이 반도체 수출 규제를 확대했다.",
        }

    def test_accepts_fenced_json_for_gateway_compatibility(self):
        parsed = _extract_json_object(
            '```json\n{"name":"새 이슈","summary":"한 줄 요약"}\n```'
        )
        self.assertEqual(parsed["name"], "새 이슈")

    def test_completion_url_accepts_base_or_full_endpoint(self):
        self.assertEqual(
            _completion_url("https://example.test/v1"),
            "https://example.test/v1/chat/completions",
        )
        self.assertEqual(
            _completion_url("https://example.test/v1/chat/completions/"),
            "https://example.test/v1/chat/completions",
        )

    def test_request_sends_representative_titles_without_article_ids(self):
        article = UnclassifiedArticle(
            article_id="internal-article-id",
            theme_id=12,
            embedding=(1.0, 0.0),
            title="미국이 대중국 반도체 수출 규제를 확대했다",
            published_at="2026-09-03T03:35:24Z",
            unclassified_at="2026-09-03T04:10:01Z",
        )
        cluster = ClusterCandidate(
            theme_id=12,
            articles=(article,),
            centroid=(1.0, 0.0),
            representatives=(article,),
            membership_confidence=0.92,
        )
        config = GmsConfig(
            api_key="test-key",
            base_url="https://example.test/v1",
            model="test-model",
        )

        request = json.loads(_request_body(config, "국제", cluster).decode("utf-8"))
        prompt_payload = json.loads(
            request["messages"][1]["content"].split("\n", maxsplit=1)[1]
        )

        self.assertEqual(
            prompt_payload["cluster"]["article_titles"],
            ["미국이 대중국 반도체 수출 규제를 확대했다"],
        )
        self.assertNotIn("article_id", request["messages"][1]["content"])

    def test_validates_existing_issue_metadata_contract(self):
        generated = validate_generated_issue(self.valid)
        self.assertEqual(generated.name, "새 반도체 규제")
        self.assertEqual(generated.summary, self.valid["summary"])

    def test_rejects_the_expanded_noncanonical_contract(self):
        value = {
            "issue_name": "새 이슈",
            "one_line_summary": "요약",
            "keywords": ["하나", "둘", "셋"],
            "duplicate_of": None,
            "confidence": 0.9,
        }
        with self.assertRaisesRegex(GmsIssueGenerationError, "exactly"):
            validate_generated_issue(value)

    def test_rejects_extra_fields(self):
        with self.assertRaisesRegex(GmsIssueGenerationError, "exactly"):
            validate_generated_issue(dict(self.valid, confidence=0.9))

    def test_rejects_summary_over_300_characters(self):
        with self.assertRaisesRegex(GmsIssueGenerationError, "summary"):
            validate_generated_issue(dict(self.valid, summary="a" * 301))


if __name__ == "__main__":
    unittest.main()
