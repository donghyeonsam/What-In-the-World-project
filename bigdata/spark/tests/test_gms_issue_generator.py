import json
import sys
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps"))

from gms_issue_generator import (  # noqa: E402
    GmsConfig,
    GmsIssueGenerationError,
    GmsRateLimitError,
    _extract_json_object,
    _extract_response_text,
    _generation_url,
    _request_body,
    generate_issue,
    validate_generated_issue_decision,
)
from issue_clustering import ClusterCandidate, UnclassifiedArticle  # noqa: E402


class GmsIssueGeneratorTest(unittest.TestCase):
    def setUp(self):
        self.valid = {
            "name": "미국 대중국 반도체 수출 규제 확대",
            "included_refs": [0, 1],
        }

    def test_accepts_fenced_json_for_gateway_compatibility(self):
        parsed = _extract_json_object(
            '```json\n{"name":"새 이슈","included_refs":[0]}\n```'
        )
        self.assertEqual(parsed["name"], "새 이슈")

    def test_generation_url_accepts_base_or_full_endpoint(self):
        self.assertEqual(
            _generation_url(
                "https://example.test/v1beta",
                "gemini-test",
                "test-key",
            ),
            "https://example.test/v1beta/models/"
            "gemini-test:generateContent?key=test-key",
        )
        self.assertEqual(
            _generation_url(
                "https://example.test/v1beta/models/gemini-test:generateContent/",
                "gemini-test",
                "test-key",
            ),
            "https://example.test/v1beta/models/"
            "gemini-test:generateContent?key=test-key",
        )

    def test_request_sends_every_candidate_with_compact_refs(self):
        first = self._article("internal-article-id", "미국 반도체 규제")
        second = self._article("another-internal-id", "중국의 별도 보복 조치")
        cluster = ClusterCandidate(
            theme_id=12,
            articles=(first, second),
            centroid=(1.0, 0.0),
            representatives=(first,),
            membership_confidence=0.92,
        )
        config = GmsConfig(
            api_key="test-key",
            base_url="https://example.test/v1",
            model="test-model",
        )

        request = json.loads(_request_body(config, "국제", cluster).decode("utf-8"))
        system_prompt = request["systemInstruction"]["parts"][0]["text"]
        user_prompt = request["contents"][0]["parts"][0]["text"]
        prompt_payload = json.loads(
            user_prompt.split("\n", maxsplit=1)[1]
        )

        self.assertEqual(
            prompt_payload["articles"],
            [
                {
                    "ref": 0,
                    "date": "2026-09-03",
                    "title": "미국 반도체 규제",
                    "summary": "미국 정부가 중국에 대한 반도체 수출 규제를 확대했다.",
                },
                {
                    "ref": 1,
                    "date": "2026-09-03",
                    "title": "중국의 별도 보복 조치",
                    "summary": "미국 정부가 중국에 대한 반도체 수출 규제를 확대했다.",
                },
            ],
        )
        self.assertNotIn("cluster", prompt_payload)
        self.assertNotIn("article_count", request["contents"][0]["parts"][0]["text"])
        self.assertNotIn(
            "hdbscan_membership_confidence",
            request["contents"][0]["parts"][0]["text"],
        )
        self.assertNotIn("article_id", request["contents"][0]["parts"][0]["text"])
        self.assertNotIn("model", request)
        self.assertEqual(
            request["generationConfig"]["responseMimeType"],
            "application/json",
        )
        self.assertEqual(
            request["generationConfig"]["responseSchema"]["type"],
            "OBJECT",
        )
        self.assertEqual(
            set(request["generationConfig"]["responseSchema"]["required"]),
            {"name", "included_refs"},
        )
        self.assertIn("theme은 후보를 모은 상위 분류", system_prompt)
        self.assertIn("특정 개수를 채우려고 인접 사건을 섞지 마라", system_prompt)
        self.assertIn("타파추라 소치밀코 지구 주택 총격", system_prompt)
        self.assertIn("칸쿤에서 마약 소량 유통 혐의 9명 기소", system_prompt)
        self.assertIn(
            "included_refs는 [0,1,2,3,4,5,6,7]",
            system_prompt,
        )
        self.assertIn("7개 ref를 그대로 반환", system_prompt)
        self.assertIn("선택된 기사 수와 무관하게", user_prompt)
        self.assertNotIn("8건", system_prompt)
        self.assertNotIn("8건", user_prompt)
        self.assertIn("판정 과정이나 설명은 출력하지 마라", user_prompt)
        self.assertNotIn(
            "discard_refs",
            user_prompt,
        )

    def test_extracts_text_from_gemini_candidate_parts(self):
        content = _extract_response_text(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": '{"name":"새로운 구체적 이슈",'},
                                {"text": '"included_refs":[0]}'},
                            ]
                        }
                    }
                ]
            }
        )
        self.assertIn("included_refs", content)

    def test_rate_limit_is_not_retried_and_exposes_retry_after(self):
        headers = Message()
        headers["Retry-After"] = "17"
        error = HTTPError(
            "https://example.test",
            429,
            "Too Many Requests",
            headers,
            None,
        )
        cluster = ClusterCandidate(
            theme_id=12,
            articles=(self._article("a-1", "미국 반도체 규제"),),
            centroid=(1.0, 0.0),
            representatives=(),
            membership_confidence=0.92,
        )
        config = GmsConfig(
            api_key="test-key",
            base_url="https://example.test/v1",
            model="test-model",
            max_attempts=3,
        )

        with patch("gms_issue_generator.urlopen", side_effect=error) as mocked:
            with self.assertRaises(GmsRateLimitError) as raised:
                generate_issue(config, "국제", cluster)

        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(raised.exception.retry_after_seconds, 17.0)

    def test_validates_issue_metadata_and_keeps_all_unselected_articles(self):
        decision = validate_generated_issue_decision(
            self.valid,
            ("a-1", "a-2", "a-3", "a-4"),
        )
        self.assertEqual(decision.issue.name, "미국 대중국 반도체 수출 규제 확대")
        self.assertEqual(decision.included_article_ids, ("a-1", "a-2"))
        self.assertEqual(decision.excluded_article_ids, ("a-3", "a-4"))

    def test_rejects_the_expanded_noncanonical_contract(self):
        value = {
            "issue_name": "새 이슈",
            "one_line_summary": "요약",
            "keywords": ["하나", "둘", "셋"],
            "duplicate_of": None,
            "confidence": 0.9,
        }
        with self.assertRaisesRegex(GmsIssueGenerationError, "exactly"):
            validate_generated_issue_decision(value, ("a-1",))

    def test_rejects_extra_fields(self):
        with self.assertRaisesRegex(GmsIssueGenerationError, "exactly"):
            validate_generated_issue_decision(
                dict(self.valid, confidence=0.9),
                ("a-1", "a-2", "a-3"),
            )

    def test_rejects_vague_issue_name(self):
        with self.assertRaisesRegex(GmsIssueGenerationError, "too vague"):
            validate_generated_issue_decision(
                {
                    "name": "사이버보안 관련 이슈",
                    "included_refs": [0],
                },
                ("a-1",),
            )

    def test_rejects_unknown_or_duplicate_article_refs(self):
        with self.assertRaisesRegex(GmsIssueGenerationError, "unknown"):
            validate_generated_issue_decision(
                dict(
                    self.valid,
                    included_refs=[0, 3],
                ),
                ("a-1", "a-2", "a-3"),
            )

        with self.assertRaisesRegex(GmsIssueGenerationError, "duplicates"):
            validate_generated_issue_decision(
                dict(
                    self.valid,
                    included_refs=[0, 0],
                ),
                ("a-1", "a-2", "a-3"),
            )

    def test_rejects_removed_discard_refs_field(self):
        with self.assertRaisesRegex(GmsIssueGenerationError, "exactly"):
            validate_generated_issue_decision(
                dict(self.valid, discard_refs=[1]),
                ("a-1", "a-2", "a-3"),
            )

    @staticmethod
    def _article(article_id: str, title: str) -> UnclassifiedArticle:
        return UnclassifiedArticle(
            article_id=article_id,
            theme_id=12,
            embedding=(1.0, 0.0),
            title=title,
            published_at="2026-09-03T03:35:24Z",
            unclassified_at="2026-09-03T04:10:01Z",
            summary="미국 정부가 중국에 대한 반도체 수출 규제를 확대했다.",
        )


if __name__ == "__main__":
    unittest.main()
