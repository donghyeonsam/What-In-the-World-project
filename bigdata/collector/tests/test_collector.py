import csv
import json
import os
import runpy
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
    def test_existing_collection_and_observation_use_separate_registries_and_limits(self):
        with patch.object(sys, "argv", ["collector"]):
            existing = collector.parse_args()
        with patch.object(sys, "argv", ["collector", "--observe-only"]):
            observation = collector.parse_args()
        self.assertFalse(existing.observe_only)
        self.assertEqual(Path(existing.registry).name, "registry.csv")
        self.assertEqual(Path(observation.registry).name, "registry_50country.csv")
        for name in (
            "max_sources_per_country_per_round", "max_fetches_per_country_per_round",
            "max_fetches_per_source_per_round", "max_articles_per_country_per_day",
            "max_articles_per_source_country_day",
        ):
            self.assertEqual(getattr(existing, name), 0)
            self.assertGreater(getattr(observation, name), 0)
        self.assertEqual({source.country for source in collector.load_sources(Path(existing.registry), False)}, {
            "Germany", "Japan", "South Korea", "United Kingdom", "United States",
        })
        observation_sources = collector.load_sources(
            Path(observation.registry), False
        )
        self.assertEqual(len({source.country for source in observation_sources}), 50)
        self.assertEqual(len(observation_sources), 1146)
        observation_counts = Counter(
            source.country for source in observation_sources
        )
        self.assertEqual(observation_counts["Belgium"], 5)
        self.assertEqual(observation_counts["France"], 5)
        self.assertEqual(observation_counts["Switzerland"], 8)
        self.assertEqual(observation_counts["Vietnam"], 5)
        self.assertTrue({
            "sudinfo.be", "lest-eclair.fr", "lunion.fr", "blick.ch",
            "vov.vn", "voh.com.vn", "baothanhhoa.vn",
            "theclinic.cl", "citynewsservice.cn", "liberoquotidiano.it",
            "vesti.kz", "awamiawaz.pk", "kwangju.co.kr", "kjdaily.com",
            "jtbc.co.kr", "telecinco.es", "three.fm", "mlive.com",
            "oregonlive.com", "syracuse.com", "sun-sentinel.com",
            "pilotonline.com",
        }.isdisjoint({source.domain for source in observation_sources}))
        self.assertEqual(observation.pending_max_age_minutes, 120)
        self.assertEqual(observation.max_pending_per_source, 100)
        self.assertEqual(observation.poll_error_quarantine_threshold, 6)
        self.assertEqual(observation.poll_error_quarantine_minutes, 360)

    def test_global47_profile_uses_free_collection_and_excludes_failed_countries(self):
        with patch.object(sys, "argv", [
            "collector", "--collection-profile", "global47",
        ]):
            args = collector.parse_args()

        self.assertEqual(Path(args.registry).name, "registry_50country.csv")
        self.assertEqual(args.exclude_countries, ["China", "Egypt", "Norway"])
        self.assertEqual(args.max_articles_per_country_per_day, 0)
        self.assertEqual(args.max_articles_per_source_country_day, 0)
        self.assertEqual(
            collector.source_daily_limit_for_profile("global47", 150),
            0,
        )
        self.assertEqual(
            collector.source_daily_limit_for_profile("legacy5", 150),
            150,
        )
        sources = collector.load_sources(
            Path(args.registry), False, args.exclude_countries
        )
        self.assertEqual(len(sources), 1142)
        self.assertEqual(len({source.country for source in sources}), 47)
        self.assertTrue(
            {"China", "Egypt", "Norway"}.isdisjoint(
                {source.country for source in sources}
            )
        )

    def test_observation_keeps_production_state_and_never_connects_to_kafka(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            production_db = output / "collection_24h_v2.db"
            production_db.write_bytes(b"production state must remain untouched")
            production_health = output / "collector.heartbeat"
            production_health.write_text("existing health", encoding="utf-8")
            with patch.object(sys, "argv", [
                "collector", "--observe-only", "--output-dir", directory,
                "--duration-minutes", "0", "--warmup-retries", "1",
            ]), patch.dict(os.environ, {"COLLECTOR_HEALTH_FILE": str(production_health)}), patch.object(
                collector, "load_sources", return_value=[make_source()]
            ), patch.object(collector, "warmup_round"), patch.object(
                collector, "final_baseline_refresh"
            ), patch.object(collector, "KafkaRawProducer", side_effect=AssertionError("Kafka forbidden")):
                collector.main()
            self.assertEqual(production_db.read_bytes(), b"production state must remain untouched")
            self.assertEqual(production_health.read_text(encoding="utf-8"), "existing health")
            report = json.loads((output / "observe/summary.json").read_text(encoding="utf-8"))
            self.assertEqual(report["collection_mode"], "observe")
            self.assertIsNone(report["source_coverage"][0]["article_success_rate_pct"])
            self.assertEqual(report["source_coverage"][0]["status"], "NOT_POLLED")
            self.assertTrue((output / "observe/country_status.csv").exists())
            self.assertTrue((output / "observe/source_status.csv").exists())

    def test_observation_fetches_and_records_articles_without_publishing(self):
        with patch.object(sys, "argv", ["collector", "--observe-only"]):
            args = collector.parse_args()
        source = make_source()
        article = make_article()
        article.published_at = collector.iso(collector.utc_now())
        body = "A detailed article sentence with meaningful reporting. " * 12
        fetched = {"success": True, "http_status": 200, "title": "Actual headline",
                   "body": body, "body_length": len(body), "elapsed_ms": 20, "error": None}
        result = {"source": source, "articles": [], "rss_status": "HTTP_304",
                  "sitemap_status": "", "latest_status": "", "elapsed_ms": 10, "error": ""}
        producer = Mock()
        with tempfile.TemporaryDirectory() as directory:
            db = collector.DB(Path(directory) / "observe.db")
            try:
                db.set_meta("collection_mode", "observe")
                db.enqueue_article(article)
                experiment_start = collector.utc_now()
                with patch.object(collector, "discover_source", return_value=result), patch.object(
                    collector, "fetch_article", return_value=fetched
                ):
                    collector.poll_round(
                        1, [source], db, args, experiment_start, producer,
                        session_id="session-1",
                    )
                producer.publish.assert_not_called()
                producer.flush_round.assert_not_called()
                self.assertEqual(db.conn.execute("SELECT SUM(fetch_success) FROM articles").fetchone()[0], 1)
                summary = collector.build_summary(
                    db, [source], experiment_start, collector.utc_now(),
                    session_id="session-1", pending_max_age_minutes=120,
                )
                self.assertEqual(summary["source_coverage"][0]["status"], "ARTICLES_ACCEPTED")
                self.assertEqual(summary["country_coverage"][0]["contributing_sources"], 1)
                self.assertEqual(summary["country_coverage"][0]["article_success_rate_pct"], 100)
                self.assertEqual(summary["article_outcomes"]["accepted"], 1)
                self.assertEqual(summary["eligible_article_success_rate_pct"], 100)
                self.assertEqual(summary["pending_processed_session"], 1)
                self.assertEqual(summary["by_round"][0]["queue_start_count"], 1)
                self.assertEqual(summary["by_round"][0]["queue_end_count"], 0)
                self.assertEqual(summary["by_round"][0]["accepted_count"], 1)
                self.assertEqual(
                    summary["country_coverage_alerts"][0]["country"],
                    "Germany",
                )
                collector.write_summary(Path(directory) / "summary.json", summary)
                with (Path(directory) / "source_status.csv").open(encoding="utf-8-sig") as report:
                    self.assertEqual(list(csv.DictReader(report))[0]["successful_articles"], "1")
                failed_poll = dict(result, error="TimeoutError: publisher did not respond")
                with patch.object(collector, "discover_source", return_value=failed_poll):
                    collector.poll_round(
                        2, [source], db, args, experiment_start, producer,
                        session_id="session-1",
                    )
                summary = collector.build_summary(
                    db, [source], experiment_start, collector.utc_now(),
                    session_id="session-1",
                )
                self.assertEqual(summary["source_coverage"][0]["status"], "POLL_ERROR")
                self.assertEqual(summary["source_coverage"][0]["successful_articles"], 1)
                self.assertEqual(summary["country_coverage"][0]["poll_errors"], 1)
            finally:
                db.close()

    def test_pending_queue_keeps_freshest_articles_and_prunes_backlog(self):
        source = make_source()
        base = collector.parse_iso("2026-09-15T00:00:00+00:00")
        with tempfile.TemporaryDirectory() as directory:
            db = collector.DB(Path(directory) / "observe.db")
            try:
                for index, minutes_ago in enumerate((180, 90, 30, 5)):
                    article = make_article(
                        f"https://example.com/news/story-{index}"
                    )
                    with patch.object(
                        collector,
                        "utc_now",
                        return_value=base - collector.timedelta(
                            minutes=minutes_ago
                        ),
                    ):
                        db.enqueue_article(article)

                with patch.object(collector, "utc_now", return_value=base):
                    pending = db.pending_for_sources(
                        [source],
                        per_source=10,
                        max_age_minutes=120,
                        max_pending_per_source=2,
                    )

                self.assertEqual(
                    [article.url for article, _source in pending],
                    [
                        "https://example.com/news/story-3",
                        "https://example.com/news/story-2",
                    ],
                )
                self.assertEqual(db.last_pending_pruned, {
                    "stale": 1,
                    "overflow": 1,
                })
                self.assertEqual(
                    db.conn.execute(
                        "SELECT COUNT(*) FROM pending_articles"
                    ).fetchone()[0],
                    2,
                )
            finally:
                db.close()

    def test_poll_circuit_breaker_skips_then_recovers_source(self):
        source = make_source()
        base = collector.parse_iso("2026-09-15T00:00:00+00:00")
        with tempfile.TemporaryDirectory() as directory:
            db = collector.DB(Path(directory) / "observe.db")
            try:
                db.record_poll_health(
                    source.source_id, True, "SITEMAP:HTTP 403",
                    quarantine_threshold=2, quarantine_minutes=60, now=base,
                )
                consecutive, until = db.record_poll_health(
                    source.source_id, True, "SITEMAP:HTTP 403",
                    quarantine_threshold=2, quarantine_minutes=60, now=base,
                )
                self.assertEqual(consecutive, 2)
                self.assertEqual(until, base + collector.timedelta(hours=1))
                pollable, skipped = db.pollable_sources([source], now=base)
                self.assertEqual(pollable, [])
                self.assertEqual([item[0] for item in skipped], [source])

                after_quarantine = base + collector.timedelta(minutes=61)
                pollable, skipped = db.pollable_sources(
                    [source], now=after_quarantine
                )
                self.assertEqual(pollable, [source])
                self.assertEqual(skipped, [])
                consecutive, until = db.record_poll_health(
                    source.source_id, False, "",
                    quarantine_threshold=2,
                    quarantine_minutes=60,
                    now=after_quarantine,
                )
                self.assertEqual(consecutive, 0)
                self.assertIsNone(until)
            finally:
                db.close()

    def test_partial_endpoint_failure_does_not_quarantine_source(self):
        source = make_source()
        partial_result = {
            "source": source,
            "articles": [],
            "rss_status": "200",
            "sitemap_status": "403",
            "latest_status": "",
            "successful_endpoints": 1,
            "elapsed_ms": 1,
            "error": "SITEMAP:HTTP 403",
        }
        with patch.object(sys, "argv", [
            "collector", "--observe-only",
            "--poll-error-quarantine-threshold", "1",
            "--poll-error-quarantine-minutes", "60",
        ]):
            args = collector.parse_args()
        with tempfile.TemporaryDirectory() as directory:
            db = collector.DB(Path(directory) / "observe.db")
            try:
                with patch.object(
                    collector, "discover_source", return_value=partial_result
                ):
                    collector.poll_round(
                        1, [source], db, args, collector.utc_now(), Mock()
                    )
                row = db.conn.execute(
                    "SELECT consecutive_errors, quarantined_until "
                    "FROM source_poll_health WHERE source_id=?",
                    (source.source_id,),
                ).fetchone()
                self.assertEqual(row, (0, None))
            finally:
                db.close()

    def test_removed_sources_prune_only_transient_runtime_state(self):
        active = make_source()
        removed = replace(
            make_source(),
            source_id="removed-source",
            source_name="removed.example",
            domain="removed.example",
            rss_urls=("https://removed.example/feed",),
        )
        removed_article = replace(
            make_article("https://removed.example/news/story"),
            source_id=removed.source_id,
            source_name=removed.source_name,
            normalized_url=collector.normalize_url(
                "https://removed.example/news/story"
            ),
            endpoint_url=removed.rss_urls[0],
        )
        with tempfile.TemporaryDirectory() as directory:
            db = collector.DB(Path(directory) / "observe.db")
            try:
                db.ensure_endpoint(
                    active.rss_urls[0], active.source_id, "RSS"
                )
                db.ensure_endpoint(
                    removed.rss_urls[0], removed.source_id, "RSS"
                )
                db.enqueue_article(removed_article)
                db.record_poll_health(
                    removed.source_id, True, "RSS:HTTP 403"
                )
                pruned = db.prune_inactive_source_state([active])
                self.assertEqual(pruned, {
                    "pending": 1,
                    "endpoints": 1,
                    "health": 1,
                })
                self.assertEqual(
                    db.conn.execute(
                        "SELECT COUNT(*) FROM endpoint_baseline"
                    ).fetchone()[0],
                    1,
                )
                self.assertEqual(
                    db.conn.execute(
                        "SELECT COUNT(*) FROM seen_articles"
                    ).fetchone()[0],
                    1,
                )
            finally:
                db.close()

    def test_article_outcomes_separate_filters_from_failures(self):
        self.assertEqual(
            collector.classify_article_outcome(False, "SOURCE_DAILY_CAP_150"),
            "filtered",
        )
        self.assertEqual(
            collector.classify_article_outcome(False, "EXACT_TITLE_DUPLICATE"),
            "filtered",
        )
        self.assertEqual(
            collector.classify_article_outcome(False, "BODY_TOO_SHORT(120)"),
            "quality_rejected",
        )
        self.assertEqual(
            collector.classify_article_outcome(False, "HTTP 403"),
            "access_failed",
        )
        self.assertEqual(
            collector.classify_article_outcome(True, None),
            "accepted",
        )

    def test_source_summary_reports_failure_categories_and_dominant_reason(self):
        source = make_source()
        now = collector.utc_now()
        failures = (
            ("one", "HTTP 403"),
            ("two", "HTTP 403"),
            ("three", "BODY_TOO_SHORT(120)"),
        )
        with tempfile.TemporaryDirectory() as directory:
            db = collector.DB(Path(directory) / "observe.db")
            try:
                for suffix, error in failures:
                    article = make_article(
                        f"https://example.com/news/{suffix}"
                    )
                    db.save_article(article, {
                        "success": False,
                        "http_status": 403 if error == "HTTP 403" else 200,
                        "body_length": 0,
                        "elapsed_ms": 10,
                        "error": error,
                    }, collector.iso(now))

                summary = collector.build_summary(
                    db, [source], now, now,
                )
                status = summary["source_coverage"][0]
                self.assertEqual(status["access_failed_articles"], 2)
                self.assertEqual(status["quality_rejected_articles"], 1)
                self.assertEqual(status["processing_failed_articles"], 0)
                self.assertEqual(status["dominant_failure_reason"], "HTTP_403")
            finally:
                db.close()

    def test_pending_queue_drains_sources_not_polled_in_current_rotation(self):
        with patch.object(sys, "argv", ["collector", "--observe-only"]):
            args = collector.parse_args()
        args.max_sources_per_country_per_round = 1
        first = make_source()
        second = replace(
            make_source(),
            source_id="source-2",
            source_name="second.example",
            domain="second.example",
            rss_urls=("https://second.example/feed",),
        )
        pending = replace(
            make_article("https://second.example/news/story"),
            source_id=second.source_id,
            source_name=second.source_name,
            normalized_url=collector.normalize_url(
                "https://second.example/news/story"
            ),
            endpoint_url=second.rss_urls[0],
        )
        fetched = {
            "success": True,
            "http_status": 200,
            "title": "Headline",
            "body": "A detailed article sentence with reporting. " * 12,
            "body_length": 500,
            "elapsed_ms": 10,
            "error": None,
        }

        def discovery_result(source, _db, _args):
            return {
                "source": source,
                "articles": [],
                "rss_status": "HTTP_304",
                "sitemap_status": "",
                "latest_status": "",
                "successful_endpoints": 1,
                "elapsed_ms": 1,
                "error": "",
            }

        with tempfile.TemporaryDirectory() as directory:
            db = collector.DB(Path(directory) / "observe.db")
            try:
                db.enqueue_article(pending)
                with patch.object(
                    collector, "discover_source", side_effect=discovery_result
                ), patch.object(
                    collector, "fetch_article", return_value=fetched
                ) as fetch:
                    collector.poll_round(
                        1, [first, second], db, args,
                        collector.utc_now(), Mock(),
                    )

                fetch.assert_called_once()
                self.assertEqual(
                    fetch.call_args.args[1].source_id,
                    second.source_id,
                )
                self.assertEqual(
                    db.conn.execute(
                        "SELECT COUNT(*) FROM pending_articles"
                    ).fetchone()[0],
                    0,
                )
            finally:
                db.close()

    def test_pending_cleanup_handles_mixed_timezone_offsets(self):
        source = make_source()
        now = collector.parse_iso("2026-09-15T00:30:00+00:00")
        old_article = make_article("https://example.com/news/old")
        fresh_article = make_article("https://example.com/news/fresh")
        with tempfile.TemporaryDirectory() as directory:
            db = collector.DB(Path(directory) / "observe.db")
            try:
                db.conn.executemany(
                    "INSERT INTO pending_articles VALUES (?, ?, ?, ?)",
                    [
                        (
                            old_article.normalized_url,
                            source.source_id,
                            json.dumps(collector.asdict(old_article)),
                            "2026-09-15T06:00:00+09:00",
                        ),
                        (
                            fresh_article.normalized_url,
                            source.source_id,
                            json.dumps(collector.asdict(fresh_article)),
                            "2026-09-15T09:00:00+09:00",
                        ),
                    ],
                )
                db.conn.commit()

                result = db.prune_pending_queue(
                    [source], max_age_minutes=120,
                    max_pending_per_source=100, now=now,
                )

                self.assertEqual(result["before_count"], 2)
                self.assertEqual(result["after_count"], 1)
                self.assertEqual(result["stale"], 1)
                self.assertEqual(result["oldest_age_minutes"], 30)
            finally:
                db.close()

    def test_observation_healthcheck_needs_no_kafka_and_rejects_stale_heartbeat(self):
        with tempfile.TemporaryDirectory() as directory:
            health = Path(directory) / "collector.heartbeat"
            health.write_text(json.dumps({"collection_mode": "observe"}), encoding="utf-8")
            with patch.dict(os.environ, {"COLLECTOR_HEALTH_FILE": str(health)}):
                with self.assertRaises(SystemExit) as fresh:
                    runpy.run_path(str(COLLECTOR_DIR / "healthcheck.py"))
                self.assertEqual(fresh.exception.code, 0)
                os.utime(health, (1, 1))
                with self.assertRaises(SystemExit) as stale:
                    runpy.run_path(str(COLLECTOR_DIR / "healthcheck.py"))
                self.assertEqual(stale.exception.code, 1)

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
        response = SimpleNamespace(status_code=200, text=html, url="https://example.com/news/story", headers={})
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
        response = SimpleNamespace(status_code=200, text=html, url="https://example.com/news/story", headers={})
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
            headers={},
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
                self.assertEqual(
                    summary["country_coverage_alerts"],
                    [{
                        "country": "Germany",
                        "reasons": [
                            "NO_ACCEPTED_ARTICLES",
                            "FEWER_THAN_3_CONTRIBUTING_SOURCES",
                        ],
                    }],
                )

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
