import sys
import sqlite3
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
from crawl_quality_v5 import extract_title, parse_datetime, read_jsonld


def make_source():
    return collector.Source(
        country="Germany",
        source_id="source-1",
        source_name="example.com",
        domain="example.com",
        homepage="https://example.com",
        rss_urls=("https://example.com/feed",),
        sitemap_urls=(),
        latest_page_urls=(),
        article_url_regex="",
        body_selector="article",
        ingestion_status="ACTIVE",
        display_name="Example News",
        timezone_name="Europe/Berlin",
    )


def make_article(url="https://example.com/news/story"):
    return collector.Article(
        source_id="source-1",
        source_name="example.com",
        country="Germany",
        url=url,
        normalized_url=collector.normalize_url(url),
        published_at=None,
        discovery_type="RSS",
        endpoint_url="https://example.com/feed",
        feed_title="Feed fallback",
    )


class CollectorQualityTests(unittest.TestCase):
    def test_kafka_event_preserves_legacy_fields_and_adds_quality_metadata(self):
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
            "published_at_estimated", "published_at_source",
            "section", "section_source",
        })
        self.assertEqual(event["source_name"], "example.com")
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
              "articleSection":"Technology",
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
        self.assertEqual(article.published_at_source, "jsonld:datePublished")
        self.assertFalse(article.published_at_estimated)
        self.assertEqual(article.section, "Technology")
        self.assertEqual(article.section_source, "json_ld")

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
                    make_article(), "Same title", "First body " * 60,
                    discovered_at, 1,
                )
                self.assertTrue(allowed)
                self.assertEqual(reason, "")

                allowed, reason = db.reserve_delivery(
                    make_article("https://example.com/news/duplicate"),
                    "Same title",
                    "Different body " * 60,
                    discovered_at,
                    300,
                )
                self.assertFalse(allowed)
                self.assertEqual(reason, "EXACT_TITLE_DUPLICATE")

                allowed, reason = db.reserve_delivery(
                    make_article("https://example.com/news/body-duplicate"),
                    "Different title",
                    "First body " * 60,
                    discovered_at,
                    300,
                )
                self.assertFalse(allowed)
                self.assertEqual(reason, "BODY_HASH_DUPLICATE")

                allowed, reason = db.reserve_delivery(
                    make_article("https://example.com/news/over-cap"),
                    "Another title",
                    "Third body " * 60,
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

    def test_naive_publication_time_uses_source_timezone(self):
        self.assertEqual(
            parse_datetime("2026-09-08 12:34:56", "Asia/Tokyo"),
            "2026-09-08T03:34:56+00:00",
        )
        self.assertEqual(
            parse_datetime("2026-09-08 12:34:56", "Asia/Seoul"),
            "2026-09-08T03:34:56+00:00",
        )
        self.assertEqual(
            parse_datetime("2026-09-08 12:34:56 CEST", "Europe/Berlin"),
            "2026-09-08T10:34:56+00:00",
        )
        self.assertEqual(
            parse_datetime("2026-09-08 12:34:56 EST", "Europe/London"),
            "2026-09-08T17:34:56+00:00",
        )

    def test_future_page_date_falls_back_to_valid_feed_date(self):
        paragraph = "A detailed article sentence with meaningful reporting. " * 12
        html = f"""
        <html><head>
          <meta property="article:published_time" content="2030-01-01T12:00:00Z">
          <meta property="og:title" content="Actual headline">
        </head><body><article><p>{paragraph}</p></article></body></html>
        """
        response = SimpleNamespace(
            status_code=200,
            text=html,
            url="https://example.com/news/story",
        )
        session = Mock()
        session.get.return_value = response
        article = make_article()
        article.published_at = "2026-09-09T05:00:00+00:00"
        article.published_at_source = "rss:published"
        args = SimpleNamespace(
            timeout_seconds=2,
            min_body_chars=100,
            published_future_tolerance_minutes=10,
        )
        fixed_now = collector.parse_iso("2026-09-10T00:00:00+00:00")
        with patch.object(collector, "robots_allowed", return_value=(True, "OK")), patch.object(
            collector,
            "get_session",
            return_value=session,
        ), patch.object(collector, "utc_now", return_value=fixed_now):
            fetched = collector.fetch_article(article, make_source(), args)
        self.assertTrue(fetched["success"])
        self.assertEqual(article.published_at, "2026-09-09T05:00:00+00:00")
        self.assertEqual(
            article.published_at_source,
            "rss:published:future_page_rejected",
        )
        self.assertFalse(article.published_at_estimated)

    def test_title_suffix_requires_source_alias_or_repetition(self):
        with tempfile.TemporaryDirectory() as directory:
            db = collector.DB(Path(directory) / "collection_24h_v2.db")
            try:
                source = make_source()
                self.assertEqual(
                    db.clean_title_suffix(
                        source,
                        "A real headline | Example News",
                        minimum_occurrences=5,
                    ),
                    "A real headline",
                )
                self.assertEqual(
                    db.clean_title_suffix(
                        source,
                        "Flood warning | 岩手日報ONLINE",
                        minimum_occurrences=5,
                        suffix_aliases=("岩手日報ONLINE",),
                    ),
                    "Flood warning",
                )
                title = "Another real headline | Repeated Publisher"
                for _ in range(4):
                    cleaned = db.clean_title_suffix(source, title, 5)
                self.assertEqual(cleaned, title)
                self.assertEqual(
                    db.clean_title_suffix(source, title, 5),
                    "Another real headline",
                )
                self.assertEqual(
                    db.clean_title_suffix(
                        source,
                        "Operating profit - down 40 percent",
                        5,
                    ),
                    "Operating profit - down 40 percent",
                )
            finally:
                db.close()

    def test_existing_article_database_is_migrated_additively(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "collection_24h_v2.db"
            connection = sqlite3.connect(path)
            connection.execute(
                """
                CREATE TABLE articles (
                    normalized_url TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    country TEXT NOT NULL,
                    original_url TEXT NOT NULL,
                    published_at TEXT,
                    discovered_at TEXT NOT NULL,
                    discovery_type TEXT NOT NULL,
                    endpoint_url TEXT NOT NULL,
                    fetch_success INTEGER NOT NULL,
                    http_status INTEGER,
                    body_length INTEGER NOT NULL,
                    fetch_elapsed_ms INTEGER NOT NULL,
                    fetch_error TEXT
                )
                """
            )
            connection.commit()
            connection.close()

            db = collector.DB(path)
            try:
                columns = {
                    row[1]
                    for row in db.conn.execute("PRAGMA table_info(articles)")
                }
                self.assertTrue({
                    "published_at_estimated",
                    "published_at_source",
                    "section",
                    "section_source",
                }.issubset(columns))
            finally:
                db.close()

    def test_v5_registry_keeps_contract_and_applies_source_changes(self):
        sources = collector.load_sources(COLLECTOR_DIR / "registry.csv", False)
        by_domain = {}
        for source in sources:
            by_domain.setdefault(source.domain, []).append(source)

        self.assertNotIn("excite.co.jp", by_domain)
        self.assertNotIn("golem.de", by_domain)
        self.assertFalse(any("docomo" in domain for domain in by_domain))
        self.assertFalse(any("prtimes" in domain for domain in by_domain))
        self.assertEqual(len(by_domain["theguardian.com"]), 1)
        self.assertEqual(by_domain["theguardian.com"][0].country, "United Kingdom")

        country_counts = Counter(source.country for source in sources)
        self.assertGreaterEqual(country_counts["Germany"], 60)
        self.assertGreaterEqual(country_counts["South Korea"], 55)
        self.assertTrue(any(source.max_items_per_poll > 200 for source in sources))
        self.assertTrue(all(source.source_name == source.domain for source in sources))

        registry = collector.pd_read_csv(COLLECTOR_DIR / "registry.csv")
        german_active = registry[
            (registry["country"] == "Germany")
            & (registry["ingestion_status"] == "ACTIVE")
            & (registry["crawl_enabled"] == True)
        ]
        focuses = Counter(german_active["coverage_focus"].fillna(""))
        self.assertGreaterEqual(focuses["TECHNOLOGY"], 7)
        self.assertGreaterEqual(focuses["CULTURE"], 3)

    def test_zdf_filter_accepts_articles_but_rejects_navigation(self):
        source = next(
            source
            for source in collector.load_sources(COLLECTOR_DIR / "registry.csv", False)
            if source.source_id == "40752"
        )
        self.assertFalse(
            collector.looks_like_article("https://www.zdfheute.de/merkliste", source)
        )
        self.assertFalse(
            collector.looks_like_article(
                "https://www.zdfheute.de/thema/ukraine-198.html",
                source,
            )
        )
        self.assertTrue(
            collector.looks_like_article(
                "https://www.zdfheute.de/politik/deutschland/example-100.html",
                source,
            )
        )

    def test_summary_marks_incomplete_24_hour_window(self):
        with tempfile.TemporaryDirectory() as directory:
            db = collector.DB(Path(directory) / "collection_24h_v2.db")
            try:
                started = collector.parse_iso("2026-09-09T00:00:00+00:00")
                ended = collector.parse_iso("2026-09-09T16:24:00+00:00")
                summary = collector.build_summary(
                    db,
                    [make_source()],
                    started,
                    ended,
                    required_window_hours=24,
                )
                self.assertFalse(summary["window_complete"])
                self.assertAlmostEqual(summary["remaining_window_hours"], 7.6)

                resumed = collector.build_summary(
                    db,
                    [make_source()],
                    started,
                    collector.parse_iso("2026-09-10T12:00:00+00:00"),
                    required_window_hours=24,
                    active_runtime_seconds=16.4 * 3600,
                )
                self.assertFalse(resumed["window_complete"])
                self.assertAlmostEqual(resumed["elapsed_hours"], 16.4)
                self.assertAlmostEqual(resumed["wall_clock_hours"], 36.0)
            finally:
                db.close()

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
