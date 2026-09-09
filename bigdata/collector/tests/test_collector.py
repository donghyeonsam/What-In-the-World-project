import sys
import tempfile
import unittest
from collections import Counter
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


COLLECTOR_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(COLLECTOR_DIR))

import collection_kafka_producer_v2 as collector
from bs4 import BeautifulSoup
from crawl_quality_v5 import extract_title, read_jsonld


def make_source():
    return collector.Source(
        country="Germany",
        source_id="source-1",
        source_name="Example News",
        domain="example.com",
        homepage="https://example.com",
        rss_urls=("https://example.com/feed",),
        sitemap_urls=(),
        latest_page_urls=(),
        article_url_regex="",
        body_selector="article",
        ingestion_status="ACTIVE",
    )


def make_article(url="https://example.com/news/story"):
    return collector.Article(
        source_id="source-1",
        source_name="Example News",
        country="Germany",
        url=url,
        normalized_url=collector.normalize_url(url),
        published_at=None,
        discovery_type="RSS",
        endpoint_url="https://example.com/feed",
        feed_title="Feed fallback",
    )


class CollectorQualityTests(unittest.TestCase):
    def test_kafka_event_contract_is_unchanged(self):
        article = make_article()
        fetched = {
            "success": True,
            "http_status": 200,
            "title": "Title",
            "body": "Body",
            "body_length": 4,
            "elapsed_ms": 12,
            "error": None,
        }
        event = collector.build_raw_article_event(
            article,
            fetched,
            "2026-09-09T00:00:00+00:00",
        )
        self.assertEqual(set(event), {
            "article_id", "source_id", "source_name", "country",
            "article_url", "published_at", "discovered_at",
            "discovery_type", "endpoint_url", "success", "http_status",
            "title", "body", "body_length", "elapsed_ms", "error",
        })
        self.assertEqual(
            event["article_id"],
            collector.make_article_id(article.normalized_url),
        )

    def test_jsonld_publisher_name_does_not_replace_article_headline(self):
        html = """
        <script type="application/ld+json">
          {"@graph":[
            {"@type":"Organization","name":"Example News"},
            {"@type":"NewsArticle","headline":"Actual headline"}
          ]}
        </script>
        """
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(extract_title(soup, read_jsonld(soup)), "Actual headline")

    def test_fetch_improves_title_body_and_publication_date_in_place(self):
        paragraph = "A detailed article sentence with meaningful reporting. " * 12
        html = f"""
        <html><head>
          <script type="application/ld+json">
            {{"@type":"NewsArticle","headline":"Actual headline",
              "datePublished":"2026-09-08T12:34:56Z"}}
          </script>
        </head><body><article><p>{paragraph}</p></article></body></html>
        """
        response = SimpleNamespace(status_code=200, text=html, url="https://example.com/news/story")
        session = Mock()
        session.get.return_value = response
        article = make_article()
        args = SimpleNamespace(timeout_seconds=2, min_body_chars=100)
        with patch.object(collector, "robots_allowed", return_value=(True, "OK")), patch.object(
            collector,
            "get_session",
            return_value=session,
        ):
            fetched = collector.fetch_article(article, make_source(), args)
        self.assertTrue(fetched["success"])
        self.assertEqual(fetched["title"], "Actual headline")
        self.assertGreater(fetched["body_length"], 100)
        self.assertEqual(article.published_at, "2026-09-08T12:34:56+00:00")

    def test_wall_page_is_rejected_without_changing_output_shape(self):
        html = "<html><head><title>Access denied</title></head><body><article><p>" + (
            "Please wait while the security system checks this request. " * 12
        ) + "</p></article></body></html>"
        response = SimpleNamespace(status_code=200, text=html, url="https://example.com/news/story")
        session = Mock()
        session.get.return_value = response
        args = SimpleNamespace(timeout_seconds=2, min_body_chars=100)
        with patch.object(collector, "robots_allowed", return_value=(True, "OK")), patch.object(
            collector,
            "get_session",
            return_value=session,
        ):
            fetched = collector.fetch_article(make_article(), make_source(), args)
        self.assertFalse(fetched["success"])
        self.assertTrue(fetched["error"].startswith("WALL_TITLE:"))
        self.assertEqual(set(fetched), {
            "success", "http_status", "title", "body", "body_length",
            "elapsed_ms", "error",
        })

    def test_title_dedup_and_daily_cap_use_additive_legacy_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            db = collector.DB(Path(directory) / "collection_24h_v2.db")
            try:
                discovered_at = "2026-09-09T00:00:00+00:00"
                allowed, reason = db.reserve_delivery(
                    make_article(), "Same title", discovered_at, 1,
                )
                self.assertTrue(allowed)
                self.assertEqual(reason, "")

                allowed, reason = db.reserve_delivery(
                    make_article("https://example.com/news/duplicate"),
                    "Same title",
                    discovered_at,
                    300,
                )
                self.assertFalse(allowed)
                self.assertEqual(reason, "EXACT_TITLE_DUPLICATE")

                allowed, reason = db.reserve_delivery(
                    make_article("https://example.com/news/over-cap"),
                    "Different title",
                    discovered_at,
                    1,
                )
                self.assertFalse(allowed)
                self.assertEqual(reason, "SOURCE_DAILY_CAP_1")

                columns = {
                    row[1]
                    for row in db.conn.execute("PRAGMA table_info(articles)").fetchall()
                }
                self.assertNotIn("title_hash", columns)
                self.assertIn("fetch_elapsed_ms", columns)
            finally:
                db.close()

    def test_rolling_quality_gate_detects_repeated_error_page(self):
        fetched = {
            "success": True,
            "http_status": 200,
            "title": "Repeated generic headline",
            "body": "Unrelated navigation and sidebar content with enough characters. " * 8,
            "body_length": 480,
            "elapsed_ms": 1,
            "error": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            db = collector.DB(Path(directory) / "collection_24h_v2.db")
            try:
                for index in range(10):
                    status, reasons = db.record_quality_sample(
                        make_article(f"https://example.com/news/{index}"),
                        fetched,
                        minimum_sample=10,
                    )
                self.assertEqual(status, "QUARANTINE")
                self.assertIn("TOP_TITLE_RATIO_GTE_30_PERCENT", reasons)
                row = db.conn.execute(
                    "SELECT sample_count, status FROM quality_source_status "
                    "WHERE source_id=?",
                    ("source-1",),
                ).fetchone()
                self.assertEqual(row, (10, "QUARANTINE"))
            finally:
                db.close()

    def test_country_domain_mismatch_guard_catches_guardian_us(self):
        source = replace(
            make_source(),
            domain="theguardian.com",
            country="United States",
        )
        self.assertTrue(collector.country_domain_mismatch(source))
        source = replace(source, country="United Kingdom")
        self.assertFalse(collector.country_domain_mismatch(source))

    def test_v5_registry_keeps_contract_and_applies_source_changes(self):
        sources = collector.load_sources(COLLECTOR_DIR / "registry.csv", False)
        by_domain = {}
        for source in sources:
            by_domain.setdefault(source.domain, []).append(source)

        self.assertNotIn("excite.co.jp", by_domain)
        self.assertNotIn("golem.de", by_domain)
        self.assertEqual(len(by_domain["theguardian.com"]), 1)
        self.assertEqual(by_domain["theguardian.com"][0].country, "United Kingdom")

        country_counts = Counter(source.country for source in sources)
        self.assertGreaterEqual(country_counts["Germany"], 60)
        self.assertGreaterEqual(country_counts["South Korea"], 55)
        self.assertTrue(any(source.max_items_per_poll > 200 for source in sources))

    def test_compose_cli_flags_remain_supported(self):
        with patch.object(sys, "argv", [
            "collector", "--run-forever", "--min-body-chars", "300",
            "--kafka-bootstrap", "kafka:29092", "--kafka-topic", "news.raw.v1",
        ]):
            args = collector.parse_args()
        self.assertTrue(args.run_forever)
        self.assertEqual(args.min_body_chars, 300)
        self.assertEqual(args.kafka_topic, "news.raw.v1")


if __name__ == "__main__":
    unittest.main()
