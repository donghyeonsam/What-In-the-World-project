#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""Kafka news collector with v5 quality controls.

Core guarantees:
- RSS / Sitemap / Latest Page supported.
- Endpoint-level baseline seeding.
- If an endpoint fails warm-up, its first later success is BASELINE ONLY.
  It can never dump old URLs as "new" merely because warm-up failed.
- published_at guard rejects articles clearly older than experiment start.
- source-level new article counts printed each round.
- final baseline refresh immediately before experiment_start.
- resume mode skips baseline refresh so downtime articles are not lost.
- SQLite state makes restart safe.
- publisher-local timestamps are normalized to UTC and future dates are guarded.
- source names are canonical domains; title suffix and body-prefix duplicates are removed.
- section and publication provenance are added without removing legacy event fields.
- summary.json explicitly marks whether the required 24-hour window is complete.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import random
import re
import sqlite3
import sys
import threading
import time
import urllib.robotparser
from collections import Counter, defaultdict, deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

import feedparser
from bs4 import BeautifulSoup
from safe_http import create_public_session

from crawl_quality_v5 import (
    body_prefix_hash,
    extract_body as extract_quality_body,
    extract_published_at,
    extract_section,
    extract_site_names,
    extract_title as extract_quality_title,
    has_long_line,
    is_wall_content,
    parse_datetime as parse_quality_datetime,
    read_jsonld,
    strip_title_suffix,
    title_body_matches,
    title_hash,
    title_suffix_candidate,
    timezone_for_country,
)

try:
    from confluent_kafka import Producer
except ImportError:
    Producer = None

USER_AGENT = "WorldNewsPoC/2.2"
TRACKING_QUERY_KEYS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "gclid", "fbclid", "igshid", "mc_cid", "mc_eid", "ref",
}
THREAD_LOCAL = threading.local()
ROBOTS_CACHE = {}
NON_ARTICLE_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".avif", ".svg", ".ico",
    ".bmp", ".tif", ".tiff", ".mp4", ".webm", ".mov", ".mp3", ".wav",
    ".ogg", ".flac", ".pdf", ".zip", ".css", ".js",
)
COLLECTION_PROFILES = ("legacy5", "global47")
PROFILE_EXCLUDED_COUNTRIES = {
    "legacy5": frozenset(),
    "global47": frozenset({"China", "Egypt", "Norway"}),
}


def source_daily_limit_for_profile(collection_profile, configured_limit):
    """Global scoring, rather than collection truncation, handles volume bias."""
    return configured_limit if collection_profile == "legacy5" else 0


def is_non_article_url(url):
    # Check the decoded path, not the query: /story?image=photo.jpg is valid.
    path = unquote(urlsplit(url).path).lower()
    return path.endswith(NON_ARTICLE_EXTENSIONS)


@dataclass(frozen=True)
class Source:
    country: str
    source_id: str
    source_name: str
    domain: str
    homepage: str
    rss_urls: tuple[str, ...]
    sitemap_urls: tuple[str, ...]
    latest_page_urls: tuple[str, ...]
    article_url_regex: str
    body_selector: str
    ingestion_status: str
    max_articles_per_day: int = 300
    max_items_per_poll: int = 0
    max_sitemap_urls_per_poll: int = 0
    domain_max_concurrency: int = 2
    min_request_interval_seconds: float = 1.5
    domain_adapter: str = ""
    display_name: str = ""
    timezone_name: str = "UTC"
    coverage_focus: str = ""
    domain_gate_required: bool = False


@dataclass
class Article:
    source_id: str
    source_name: str
    country: str
    url: str
    normalized_url: str
    published_at: Optional[str]
    discovery_type: str
    endpoint_url: str
    feed_title: str = ""
    feed_categories: tuple[str, ...] = ()
    published_at_source: str = ""
    published_at_estimated: bool = False
    section: str = ""
    section_source: str = ""
    title_suffix_aliases: tuple[str, ...] = ()


def utc_now():
    return datetime.now(timezone.utc)


def iso(dt):
    return dt.astimezone(timezone.utc).isoformat() if dt else None


def parse_iso(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def safe(v):
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in {"nan", "none", "null"} else s


def classify_article_outcome(fetch_success, error):
    """Separate accepted articles, expected exclusions, and real failures."""
    if fetch_success:
        return "accepted"
    reason = safe(error).upper()
    if (
        "_DAILY_CAP_" in reason
        or "DUPLICATE" in reason
        or reason.startswith("OLD_")
        or reason.startswith("NON_ARTICLE_")
    ):
        return "filtered"
    if (
        reason.startswith("SOURCE_QUALITY_GATE:")
        or reason.startswith("BODY_TOO_SHORT")
        or reason.startswith("TITLE_MISSING")
        or reason.startswith("WALL_")
        or reason.startswith("NO_BODY_LINE_")
        or "DOMAIN_MISMATCH" in reason
    ):
        return "quality_rejected"
    if (
        reason.startswith("ROBOTS_DISALLOW")
        or reason.startswith("HTTP ")
        or "TIMEOUT" in reason
        or "CONNECTION" in reason
        or "TOOMANYREDIRECTS" in reason
        or "CONTENTDECODINGERROR" in reason
        or "BLOCKEDREQUEST" in reason
    ):
        return "access_failed"
    return "processing_failed"


def summarize_failure_reason(error):
    """Collapse detailed fetch errors into stable report-friendly reason codes."""
    reason = safe(error).upper()
    if not reason:
        return "UNKNOWN"
    if reason.startswith("HTTP "):
        return reason.replace(" ", "_", 1)
    if reason.startswith("SOURCE_QUALITY_GATE:"):
        return "SOURCE_QUALITY_GATE"
    reason = reason.split(":", 1)[0]
    reason = re.sub(r"\([^)]*\)$", "", reason)
    return reason or "UNKNOWN"


def split_urls(value):
    out = []
    for x in safe(value).split("|"):
        x = x.strip()
        if x and x not in out:
            out.append(x)
    return tuple(out)


def normalize_url(url):
    if not url:
        return ""
    p = urlsplit(url.strip())
    scheme = (p.scheme or "https").lower()
    host = (p.hostname or "").lower().removeprefix("www.")
    if not host:
        return ""
    path = re.sub(r"/{2,}", "/", p.path or "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]

    qs = []
    for k, v in parse_qsl(p.query, keep_blank_values=True):
        if k.lower() not in TRACKING_QUERY_KEYS and not k.lower().startswith("utm_"):
            qs.append((k, v))
    qs.sort()
    return urlunsplit((scheme, host, path, urlencode(qs), ""))


COUNTRY_TLDS = {
    "Argentina": (".ar",),
    "Australia": (".au",),
    "Austria": (".at",),
    "Bangladesh": (".bd",),
    "Belgium": (".be",),
    "Brazil": (".br",),
    "Canada": (".ca",),
    "Chile": (".cl",),
    "China": (".cn",),
    # .co is widely used by publishers outside Colombia.
    "Czech Republic": (".cz",),
    "Denmark": (".dk",),
    "Egypt": (".eg",),
    "Finland": (".fi",),
    "France": (".fr",),
    "Germany": (".de",),
    "Hong Kong": (".hk",),
    "India": (".in",),
    "Indonesia": (".id",),
    "Iran": (".ir",),
    "Iraq": (".iq",),
    "Ireland": (".ie",),
    "Israel": (".il",),
    "Italy": (".it",),
    "Japan": (".jp",),
    "Kazakhstan": (".kz",),
    "Malaysia": (".my",),
    "Mexico": (".mx",),
    "Netherlands": (".nl",),
    "Norway": (".no",),
    "Pakistan": (".pk",),
    "Peru": (".pe",),
    "Philippines": (".ph",),
    "Poland": (".pl",),
    "Portugal": (".pt",),
    "Romania": (".ro",),
    "Russia": (".ru",),
    "Saudi Arabia": (".sa",),
    "Singapore": (".sg",),
    "South Africa": (".za",),
    "South Korea": (".kr",),
    "Spain": (".es",),
    "Sweden": (".se",),
    "Switzerland": (".ch",),
    "Thailand": (".th",),
    "Turkey": (".tr",),
    "United Arab Emirates": (".ae",),
    "United Kingdom": (".uk",),
    "United States": (".us",),
    "Vietnam": (".vn",),
}
DOMAIN_COUNTRY_OVERRIDES = {
    "theguardian.com": "United Kingdom",
}


def country_domain_mismatch(source):
    domain = source.domain.lower().removeprefix("www.")
    expected = DOMAIN_COUNTRY_OVERRIDES.get(domain)
    if expected:
        return source.country != expected
    for country, suffixes in COUNTRY_TLDS.items():
        if not source.domain_gate_required and country not in {
            "Germany", "Japan", "South Korea", "United Kingdom", "United States",
        }:
            continue
        if domain.endswith(suffixes):
            return source.country != country
    return False


def fair_sources(sources, round_no, per_country=0):
    """Rotate each country's publishers, then interleave countries.

    Use a fixed stride rather than `round_no % n`: the latter repeatedly
    polls overlapping windows and gives large countries a slow rotation.
    """
    grouped = defaultdict(list)
    for source in sources:
        grouped[source.country].append(source)
    countries = sorted(grouped)
    offset = (round_no - 1) % len(countries) if countries else 0
    countries = countries[offset:] + countries[:offset]
    queues = {}
    for country in countries:
        publishers = sorted(grouped[country], key=lambda s: s.source_id)
        count = min(per_country, len(publishers)) if per_country else len(publishers)
        start = ((round_no - 1) * count) % len(publishers)
        queues[country] = deque(
            publishers[(start + index) % len(publishers)] for index in range(count)
        )
    ordered = []
    while any(queues.values()):
        for country in countries:
            if queues[country]:
                ordered.append(queues[country].popleft())
    return ordered


def fair_articles(candidates, sources, round_no, per_country, per_source):
    queues = defaultdict(deque)
    for article, source in candidates:
        queues[source.source_id].append((article, source))
    ordered_sources = fair_sources(sources, round_no)
    country_counts = Counter()
    source_counts = Counter()
    ordered = []
    while True:
        progressed = False
        for source in ordered_sources:
            if not queues[source.source_id]:
                continue
            if per_country and country_counts[source.country] >= per_country:
                continue
            if per_source and source_counts[source.source_id] >= per_source:
                continue
            ordered.append(queues[source.source_id].popleft())
            source_counts[source.source_id] += 1
            country_counts[source.country] += 1
            progressed = True
        if not progressed:
            return ordered



def make_article_id(normalized_url):
    """Create a deterministic article id from the normalized URL."""
    value = (normalized_url or "").strip()
    if not value:
        return ""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def extract_article_title(html_text):
    """Extract the best-effort article title from the fetched HTML."""
    if not html_text:
        return ""

    soup = BeautifulSoup(html_text, "html.parser")
    return extract_quality_title(soup, read_jsonld(soup))


def build_raw_article_event(article, fetched, discovered_at):
    """Build the backward-compatible payload used by news.raw.v1."""
    return {
        "article_id": make_article_id(article.normalized_url),
        "source_id": article.source_id,
        "source_name": article.source_name,
        "country": article.country,
        "article_url": article.url,
        "published_at": article.published_at,
        "discovered_at": discovered_at,
        "discovery_type": article.discovery_type,
        "endpoint_url": article.endpoint_url,
        "success": fetched["success"],
        "http_status": fetched["http_status"],
        "title": fetched.get("title", ""),
        "body": fetched.get("body", ""),
        "body_length": fetched["body_length"],
        "elapsed_ms": fetched["elapsed_ms"],
        "error": fetched["error"],
        "published_at_estimated": article.published_at_estimated,
        "published_at_source": article.published_at_source,
        "section": article.section or None,
        "section_source": article.section_source or None,
    }



class KafkaRawProducer:
    """Publish successfully fetched raw articles to Kafka."""

    def __init__(self, bootstrap_servers, topic, failed_path):
        if Producer is None:
            raise RuntimeError(
                "confluent-kafka is not installed. Run: pip install confluent-kafka"
            )

        self.topic = topic
        self.failed_path = failed_path
        self._delivered = 0
        self._failed = 0
        self.producer = Producer({
            "bootstrap.servers": bootstrap_servers,
            "client.id": "news-collector",
            "acks": "all",
            "enable.idempotence": True,
            "compression.type": "snappy",
            "delivery.timeout.ms": 30000,
        })

        # Fail fast when the broker cannot be reached.
        self.producer.list_topics(timeout=10)

    def _delivery_callback(self, err, msg):
        if err is None:
            self._delivered += 1
            return

        self._failed += 1
        try:
            event = json.loads(msg.value().decode("utf-8"))
        except Exception:
            event = {
                "article_id": (
                    msg.key().decode("utf-8", errors="replace")
                    if msg.key() else None
                )
            }
        self._write_failed(event, str(err))

    def publish(self, event):
        """Queue one event. Kafka key is article_id."""
        payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        article_id = event["article_id"]

        try:
            self.producer.produce(
                self.topic,
                key=article_id,
                value=payload,
                callback=self._delivery_callback,
            )
            # Serve delivery callbacks and free local producer queue space.
            self.producer.poll(0)
            return True
        except BufferError:
            # Backpressure: wait briefly, then retry the same record once.
            self.producer.flush(5)
            try:
                self.producer.produce(
                    self.topic,
                    key=article_id,
                    value=payload,
                    callback=self._delivery_callback,
                )
                self.producer.poll(0)
                return True
            except Exception as e:
                self._failed += 1
                self._write_failed(event, f"{type(e).__name__}: {e}")
                return False
        except Exception as e:
            self._failed += 1
            self._write_failed(event, f"{type(e).__name__}: {e}")
            return False

    def flush_round(self):
        """Wait for this round's queued records to be acknowledged by Kafka."""
        delivered_before = self._delivered
        failed_before = self._failed
        remaining = self.producer.flush(30)
        return {
            "delivered": self._delivered - delivered_before,
            "failed": self._failed - failed_before,
            "remaining": remaining,
        }

    def close(self):
        self.producer.flush(30)

    def _write_failed(self, event, error):
        row = {"error": error, "event": event, "failed_at": iso(utc_now())}
        with self.failed_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

def get_session():
    s = getattr(THREAD_LOCAL, "session", None)
    if s is None:
        s = create_public_session()
        s.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
        })
        THREAD_LOCAL.session = s
    return s


class DomainLimiter:
    """Enforce the registry's per-domain concurrency and request interval."""

    def __init__(self, sources):
        self.lock = threading.Lock()
        policies = {}
        for source in sources:
            domain = source.domain.lower().removeprefix("www.")
            current = policies.get(domain)
            policy = (
                source.domain_max_concurrency,
                source.min_request_interval_seconds,
            )
            if current:
                policy = (min(current[0], policy[0]), max(current[1], policy[1]))
            policies[domain] = policy
        self.semaphores = {
            domain: threading.BoundedSemaphore(policy[0])
            for domain, policy in policies.items()
        }
        self.intervals = {domain: policy[1] for domain, policy in policies.items()}
        self.next_allowed = {}

    def run(self, source, function, *args, **kwargs):
        domain = source.domain.lower().removeprefix("www.")
        semaphore = self.semaphores[domain]
        with semaphore:
            with self.lock:
                now = time.monotonic()
                request_at = max(now, self.next_allowed.get(domain, now))
                self.next_allowed[domain] = request_at + self.intervals[domain]
            wait = request_at - now
            if wait > 0:
                time.sleep(wait)
            return function(*args, **kwargs)


def source_get(source, args, url, **kwargs):
    headers = dict(kwargs.pop("headers", {}) or {})
    if source.domain_adapter == "GOLEM_CONSENT":
        headers.setdefault("Cookie", "consent=true; cookieconsent_status=allow")
    limiter = getattr(args, "domain_limiter", None)
    if limiter is None:
        return get_session().get(url, headers=headers, **kwargs)
    return limiter.run(
        source,
        get_session().get,
        url,
        headers=headers,
        **kwargs,
    )


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;

CREATE TABLE IF NOT EXISTS run_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS endpoint_baseline (
    endpoint_url TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    discovery_type TEXT NOT NULL,
    baseline_ready INTEGER NOT NULL DEFAULT 0,
    baseline_seeded_at TEXT,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS endpoint_http_state (
    endpoint_url TEXT PRIMARY KEY,
    etag TEXT,
    last_modified TEXT,
    last_status INTEGER,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS seen_articles (
    normalized_url TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    country TEXT NOT NULL,
    original_url TEXT NOT NULL,
    published_at TEXT,
    first_seen_at TEXT NOT NULL,
    seen_reason TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accepted_title_hashes (
    title_hash TEXT PRIMARY KEY,
    normalized_url TEXT NOT NULL,
    source_id TEXT NOT NULL,
    accepted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accepted_body_hashes (
    body_hash TEXT PRIMARY KEY,
    normalized_url TEXT NOT NULL,
    source_id TEXT NOT NULL,
    accepted_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS title_suffix_counts (
    suffix_hash TEXT PRIMARY KEY,
    suffix_text TEXT NOT NULL,
    occurrence_count INTEGER NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_daily_accepts (
    normalized_url TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    published_day TEXT NOT NULL,
    accepted_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_source_daily_accepts
ON source_daily_accepts(source_id, published_day);

CREATE TABLE IF NOT EXISTS country_daily_accepts (
    normalized_url TEXT PRIMARY KEY,
    country TEXT NOT NULL,
    source_id TEXT NOT NULL,
    accepted_day TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_country_daily_accepts
ON country_daily_accepts(country, accepted_day, source_id);

CREATE TABLE IF NOT EXISTS pending_articles (
    normalized_url TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    article_json TEXT NOT NULL,
    queued_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pending_articles_source
ON pending_articles(source_id, queued_at);

CREATE TABLE IF NOT EXISTS source_poll_health (
    source_id TEXT PRIMARY KEY,
    consecutive_errors INTEGER NOT NULL DEFAULT 0,
    total_errors INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    quarantined_until TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS quality_samples (
    normalized_url TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    title_hash TEXT,
    title_body_match INTEGER NOT NULL,
    has_long_line INTEGER NOT NULL,
    published_at_present INTEGER NOT NULL,
    wall_content INTEGER NOT NULL,
    sampled_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quality_samples_source
ON quality_samples(source_id);

CREATE TABLE IF NOT EXISTS quality_source_status (
    source_id TEXT PRIMARY KEY,
    sample_count INTEGER NOT NULL,
    top_title_ratio REAL NOT NULL,
    title_body_match_ratio REAL NOT NULL,
    long_line_ratio REAL NOT NULL,
    published_at_missing_ratio REAL NOT NULL,
    status TEXT NOT NULL,
    reasons TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS articles (
    normalized_url TEXT PRIMARY KEY,
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    country TEXT NOT NULL,
    original_url TEXT NOT NULL,
    published_at TEXT,
    published_at_estimated INTEGER NOT NULL DEFAULT 0,
    published_at_source TEXT,
    section TEXT,
    section_source TEXT,
    discovered_at TEXT NOT NULL,
    discovery_type TEXT NOT NULL,
    endpoint_url TEXT NOT NULL,
    fetch_success INTEGER NOT NULL,
    http_status INTEGER,
    body_length INTEGER NOT NULL,
    fetch_elapsed_ms INTEGER NOT NULL,
    fetch_error TEXT
);

CREATE TABLE IF NOT EXISTS poll_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_no INTEGER NOT NULL,
    source_id TEXT NOT NULL,
    source_name TEXT NOT NULL,
    country TEXT NOT NULL,
    polled_at TEXT NOT NULL,
    discovered_total INTEGER NOT NULL,
    baseline_seeded_count INTEGER NOT NULL,
    old_published_filtered INTEGER NOT NULL,
    new_article_count INTEGER NOT NULL,
    rss_status TEXT,
    sitemap_status TEXT,
    latest_status TEXT,
    elapsed_ms INTEGER NOT NULL,
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_articles_country_time
ON articles(country, discovered_at);

CREATE INDEX IF NOT EXISTS idx_poll_round
ON poll_logs(round_no);

CREATE TABLE IF NOT EXISTS round_metrics (
    round_no INTEGER PRIMARY KEY,
    session_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    ended_at TEXT NOT NULL,
    queue_start_count INTEGER NOT NULL,
    discovered_count INTEGER NOT NULL,
    selected_count INTEGER NOT NULL,
    processed_count INTEGER NOT NULL,
    accepted_count INTEGER NOT NULL,
    dropped_stale INTEGER NOT NULL,
    dropped_overflow INTEGER NOT NULL,
    queue_end_count INTEGER NOT NULL,
    queue_oldest_age_minutes REAL NOT NULL,
    elapsed_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_round_metrics_session
ON round_metrics(session_id, round_no);
"""


class DB:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self._ensure_column(
            "articles",
            "published_at_estimated",
            "INTEGER NOT NULL DEFAULT 0",
        )
        self._ensure_column("articles", "published_at_source", "TEXT")
        self._ensure_column("articles", "section", "TEXT")
        self._ensure_column("articles", "section_source", "TEXT")
        # Preserve quota usage when resuming a v5 database.
        self.conn.execute(
            "INSERT OR IGNORE INTO country_daily_accepts "
            "SELECT s.normalized_url, a.country, s.source_id, substr(s.accepted_at, 1, 10) "
            "FROM source_daily_accepts s JOIN articles a USING(normalized_url)"
        )
        self._remove_non_article_quality_samples()
        self.conn.commit()
        self.lock = threading.Lock()

    def _ensure_column(self, table, column, definition):
        columns = {
            row[1]
            for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            self.conn.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
            )

    def _remove_non_article_quality_samples(self):
        # Older sitemap parsing sampled image files as failed articles. Remove
        # only those derived quality samples, preserving article/error history
        # and quota usage. Remaining real samples are evaluated on the next fetch.
        invalid = [
            (url, source_id) for url, source_id in self.conn.execute(
                "SELECT normalized_url, source_id FROM quality_samples"
            ).fetchall() if is_non_article_url(url)
        ]
        if invalid:
            self.conn.executemany(
                "DELETE FROM quality_samples WHERE normalized_url=? AND source_id=?",
                invalid,
            )
            self.conn.executemany(
                "DELETE FROM quality_source_status WHERE source_id=?",
                [(source_id,) for source_id in {source_id for _, source_id in invalid}],
            )
            print(f"[Quality repair] Removed {len(invalid)} non-article samples")

    def close(self):
        with self.lock:
            self.conn.commit()
            self.conn.close()

    def get_meta(self, key):
        with self.lock:
            r = self.conn.execute("SELECT value FROM run_meta WHERE key=?", (key,)).fetchone()
        return r[0] if r else None

    def set_meta(self, key, value):
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO run_meta(key, value) VALUES(?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (key, value),
            )
            self.conn.commit()

    def _increment_meta_locked(self, key, amount):
        if not amount:
            return
        self.conn.execute(
            """
            INSERT INTO run_meta(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value=CAST(value AS INTEGER) + CAST(excluded.value AS INTEGER)
            """,
            (key, str(int(amount))),
        )

    def pollable_sources(self, sources, now=None):
        """Return active sources while a failed source's circuit is open."""
        now = now or utc_now()
        with self.lock:
            quarantine = dict(self.conn.execute(
                "SELECT source_id, quarantined_until FROM source_poll_health "
                "WHERE quarantined_until IS NOT NULL"
            ).fetchall())
        pollable = []
        skipped = []
        for source in sources:
            until = parse_iso(quarantine.get(source.source_id))
            if until and until > now:
                skipped.append((source, until))
            else:
                pollable.append(source)
        return pollable, skipped

    def record_poll_health(
        self,
        source_id,
        failed,
        error,
        quarantine_threshold=0,
        quarantine_minutes=0,
        now=None,
    ):
        """Update consecutive full-source failures and open the circuit if needed."""
        now = now or utc_now()
        now_text = iso(now)
        with self.lock:
            row = self.conn.execute(
                "SELECT consecutive_errors, total_errors, quarantined_until "
                "FROM source_poll_health WHERE source_id=?",
                (source_id,),
            ).fetchone()
            consecutive, total, prior_until = row or (0, 0, None)
            if failed:
                consecutive += 1
                total += 1
                quarantined_until = prior_until
                if (
                    quarantine_threshold
                    and quarantine_minutes
                    and consecutive >= quarantine_threshold
                ):
                    quarantined_until = iso(
                        now + timedelta(minutes=quarantine_minutes)
                    )
            else:
                consecutive = 0
                quarantined_until = None
                error = ""
            self.conn.execute(
                """
                INSERT INTO source_poll_health(
                    source_id, consecutive_errors, total_errors, last_error,
                    quarantined_until, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    consecutive_errors=excluded.consecutive_errors,
                    total_errors=excluded.total_errors,
                    last_error=excluded.last_error,
                    quarantined_until=excluded.quarantined_until,
                    updated_at=excluded.updated_at
                """,
                (
                    source_id, consecutive, total, safe(error),
                    quarantined_until, now_text,
                ),
            )
            self.conn.commit()
        return consecutive, parse_iso(quarantined_until)

    def prune_inactive_source_state(self, sources):
        """Drop only transient state for sources removed from the registry."""
        source_ids = [(source.source_id,) for source in sources]
        if not source_ids:
            return {"pending": 0, "endpoints": 0, "health": 0}
        with self.lock:
            self.conn.execute(
                "CREATE TEMP TABLE IF NOT EXISTS active_registry_sources "
                "(source_id TEXT PRIMARY KEY)"
            )
            self.conn.execute("DELETE FROM active_registry_sources")
            self.conn.executemany(
                "INSERT INTO active_registry_sources(source_id) VALUES (?)",
                source_ids,
            )
            removed = {}
            for table in (
                "pending_articles", "endpoint_baseline", "source_poll_health",
            ):
                removed[table] = self.conn.execute(
                    f"DELETE FROM {table} WHERE NOT EXISTS ("
                    "SELECT 1 FROM active_registry_sources a "
                    f"WHERE a.source_id={table}.source_id)"
                ).rowcount
            self.conn.execute("DROP TABLE active_registry_sources")
            self.conn.commit()
        return {
            "pending": max(removed["pending_articles"], 0),
            "endpoints": max(removed["endpoint_baseline"], 0),
            "health": max(removed["source_poll_health"], 0),
        }

    def ensure_endpoint(self, endpoint_url, source_id, discovery_type):
        with self.lock:
            self.conn.execute(
                """
                INSERT OR IGNORE INTO endpoint_baseline(
                    endpoint_url, source_id, discovery_type, baseline_ready
                ) VALUES (?, ?, ?, 0)
                """,
                (endpoint_url, source_id, discovery_type),
            )
            self.conn.commit()

    def endpoint_ready(self, endpoint_url):
        with self.lock:
            r = self.conn.execute(
                "SELECT baseline_ready FROM endpoint_baseline WHERE endpoint_url=?",
                (endpoint_url,),
            ).fetchone()
        return bool(r and r[0] == 1)

    def mark_endpoint_ready(self, endpoint_url):
        with self.lock:
            self.conn.execute(
                """
                UPDATE endpoint_baseline
                SET baseline_ready=1, baseline_seeded_at=?, last_error=NULL
                WHERE endpoint_url=?
                """,
                (iso(utc_now()), endpoint_url),
            )
            self.conn.commit()

    def set_endpoint_error(self, endpoint_url, error):
        with self.lock:
            self.conn.execute(
                "UPDATE endpoint_baseline SET last_error=? WHERE endpoint_url=?",
                (error, endpoint_url),
            )
            self.conn.commit()

    def get_http_state(self, endpoint_url):
        with self.lock:
            r = self.conn.execute(
                "SELECT etag, last_modified FROM endpoint_http_state WHERE endpoint_url=?",
                (endpoint_url,),
            ).fetchone()
        return (r[0], r[1]) if r else (None, None)

    def save_http_state(self, endpoint_url, etag, last_modified, status):
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO endpoint_http_state(
                    endpoint_url, etag, last_modified, last_status, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(endpoint_url) DO UPDATE SET
                    etag=excluded.etag,
                    last_modified=excluded.last_modified,
                    last_status=excluded.last_status,
                    updated_at=excluded.updated_at
                """,
                (endpoint_url, etag, last_modified, status, iso(utc_now())),
            )
            self.conn.commit()

    def mark_seen(self, article, reason):
        with self.lock:
            cur = self.conn.execute(
                """
                INSERT OR IGNORE INTO seen_articles(
                    normalized_url, source_id, country, original_url,
                    published_at, first_seen_at, seen_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article.normalized_url, article.source_id, article.country,
                    article.url, article.published_at, iso(utc_now()), reason,
                ),
            )
            self.conn.commit()
            return cur.rowcount == 1

    def clean_title_suffix(
        self,
        source,
        title,
        minimum_occurrences,
        suffix_aliases=(),
    ):
        suffix, _head = title_suffix_candidate(title)
        if not suffix:
            return safe(title)
        suffix_digest = title_hash(suffix)
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO title_suffix_counts(
                    suffix_hash, suffix_text, occurrence_count, updated_at
                ) VALUES (?, ?, 1, ?)
                ON CONFLICT(suffix_hash) DO UPDATE SET
                    occurrence_count=occurrence_count + 1,
                    suffix_text=excluded.suffix_text,
                    updated_at=excluded.updated_at
                """,
                (suffix_digest, suffix, iso(utc_now())),
            )
            count = self.conn.execute(
                "SELECT occurrence_count FROM title_suffix_counts "
                "WHERE suffix_hash=?",
                (suffix_digest,),
            ).fetchone()[0]
            self.conn.commit()

        domain_label = source.domain.split(".", 1)[0]
        known_suffixes = (
            source.source_name,
            source.display_name,
            source.domain,
            domain_label,
            *suffix_aliases,
        )
        return strip_title_suffix(
            title,
            known_suffixes=known_suffixes,
            observed_count=count,
            minimum_occurrences=minimum_occurrences,
        )

    def record_quality_sample(self, article, fetched, minimum_sample):
        if is_non_article_url(article.url) or safe(fetched.get("error")).startswith("NON_ARTICLE_"):
            return "REVIEW", ["NON_ARTICLE_CONTENT"]
        title = safe(fetched.get("title"))
        body = safe(fetched.get("body"))
        digest = title_hash(title) if title else None
        wall = safe(fetched.get("error")).startswith("WALL_")

        with self.lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO quality_samples(
                    normalized_url, source_id, title_hash, title_body_match,
                    has_long_line, published_at_present, wall_content, sampled_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article.normalized_url,
                    article.source_id,
                    digest,
                    1 if title and body and title_body_matches(title, body) else 0,
                    1 if has_long_line(body) else 0,
                    1 if article.published_at and not article.published_at_estimated else 0,
                    1 if wall else 0,
                    iso(utc_now()),
                ),
            )
            totals = self.conn.execute(
                """
                SELECT COUNT(*), COALESCE(SUM(title_body_match), 0),
                       COALESCE(SUM(has_long_line), 0),
                       COALESCE(SUM(published_at_present), 0),
                       COALESCE(SUM(wall_content), 0)
                FROM quality_samples WHERE source_id=?
                """,
                (article.source_id,),
            ).fetchone()
            top_title_count = self.conn.execute(
                """
                SELECT COALESCE(MAX(article_count), 0)
                FROM (
                    SELECT COUNT(*) AS article_count
                    FROM quality_samples
                    WHERE source_id=? AND title_hash IS NOT NULL
                    GROUP BY title_hash
                )
                """,
                (article.source_id,),
            ).fetchone()[0]

            count, match_count, long_count, published_count, wall_count = totals
            top_ratio = top_title_count / count if count else 0.0
            match_ratio = match_count / count if count else 0.0
            long_ratio = long_count / count if count else 0.0
            missing_ratio = 1 - (published_count / count) if count else 0.0
            reasons = []
            if count >= minimum_sample:
                if top_ratio >= 0.30:
                    reasons.append("TOP_TITLE_RATIO_GTE_30_PERCENT")
                if match_ratio < 0.60:
                    reasons.append("TITLE_BODY_MATCH_RATIO_LT_60_PERCENT")
                if published_count == 0:
                    reasons.append("PUBLISHED_AT_REAL_MISSING_100_PERCENT")
                if wall_count:
                    reasons.append("WALL_OR_ERROR_CONTENT")

            hard_reasons = {
                "TOP_TITLE_RATIO_GTE_30_PERCENT",
                "TITLE_BODY_MATCH_RATIO_LT_60_PERCENT",
                "WALL_OR_ERROR_CONTENT",
            }
            if any(reason in hard_reasons for reason in reasons):
                status = "QUARANTINE"
            elif reasons:
                status = "REVIEW"
            else:
                status = "PASS"

            self.conn.execute(
                """
                INSERT INTO quality_source_status(
                    source_id, sample_count, top_title_ratio,
                    title_body_match_ratio, long_line_ratio,
                    published_at_missing_ratio, status, reasons, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    sample_count=excluded.sample_count,
                    top_title_ratio=excluded.top_title_ratio,
                    title_body_match_ratio=excluded.title_body_match_ratio,
                    long_line_ratio=excluded.long_line_ratio,
                    published_at_missing_ratio=excluded.published_at_missing_ratio,
                    status=excluded.status,
                    reasons=excluded.reasons,
                    updated_at=excluded.updated_at
                """,
                (
                    article.source_id,
                    count,
                    top_ratio,
                    match_ratio,
                    long_ratio,
                    missing_ratio,
                    status,
                    "|".join(reasons),
                    iso(utc_now()),
                ),
            )
            self.conn.commit()
            return status, reasons

    def enqueue_article(self, article):
        # Discovery and the durable fetch queue must commit together: a restart
        # must not leave a seen URL that was never queued for extraction.
        with self.lock:
            now = iso(utc_now())
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO seen_articles "
                "(normalized_url, source_id, country, original_url, published_at, first_seen_at, seen_reason) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (article.normalized_url, article.source_id, article.country,
                 article.url, article.published_at, now, "NEW_DISCOVERY"),
            )
            if cur.rowcount:
                self.conn.execute(
                    "INSERT OR IGNORE INTO pending_articles VALUES (?, ?, ?, ?)",
                    (article.normalized_url, article.source_id,
                     json.dumps(asdict(article), ensure_ascii=False), now),
                )
            self.conn.commit()
            return bool(cur.rowcount)

    def pending_snapshot(self, now=None):
        """Return queue size and age without mutating pending work."""
        now = now or utc_now()
        with self.lock:
            count, oldest = self.conn.execute(
                "SELECT COUNT(*), MIN(queued_at) FROM pending_articles"
            ).fetchone()
        oldest_dt = parse_iso(oldest)
        oldest_age_minutes = (
            max((now - oldest_dt).total_seconds() / 60, 0)
            if oldest_dt else 0
        )
        return {
            "count": int(count or 0),
            "oldest_at": oldest or "",
            "oldest_age_minutes": round(oldest_age_minutes, 1),
        }

    def prune_pending_queue(
        self,
        sources,
        max_age_minutes=1440,
        max_pending_per_source=0,
        now=None,
    ):
        """Apply queue retention limits and report the exact cleanup result."""
        now = now or utc_now()
        before = self.pending_snapshot(now)
        with self.lock:
            # Use SQLite datetime conversion instead of lexical comparison so
            # old databases with mixed timezone offsets are pruned correctly.
            stale = self.conn.execute(
                "DELETE FROM pending_articles "
                "WHERE datetime(queued_at) < datetime(?)",
                (iso(now - timedelta(minutes=max_age_minutes)),),
            ).rowcount if max_age_minutes else 0
            overflow = 0
            for source in sources:
                if max_pending_per_source:
                    overflow += self.conn.execute(
                        """
                        DELETE FROM pending_articles
                        WHERE source_id=? AND normalized_url NOT IN (
                            SELECT normalized_url FROM pending_articles
                            WHERE source_id=?
                            ORDER BY queued_at DESC, normalized_url DESC
                            LIMIT ?
                        )
                        """,
                        (
                            source.source_id,
                            source.source_id,
                            max_pending_per_source,
                        ),
                    ).rowcount
            self._increment_meta_locked("pending_dropped_stale", stale)
            self._increment_meta_locked("pending_dropped_overflow", overflow)
            self.conn.commit()
        after = self.pending_snapshot(now)
        self.last_pending_pruned = {
            "stale": max(stale, 0),
            "overflow": max(overflow, 0),
        }
        return {
            "before_count": before["count"],
            "after_count": after["count"],
            "stale": max(stale, 0),
            "overflow": max(overflow, 0),
            "oldest_age_minutes": after["oldest_age_minutes"],
        }

    def pending_for_sources(
        self,
        sources,
        per_source,
        max_age_minutes=1440,
        max_pending_per_source=0,
    ):
        self.prune_pending_queue(
            sources,
            max_age_minutes,
            max_pending_per_source,
        )
        candidates = []
        with self.lock:
            for source in sources:
                rows = self.conn.execute(
                    "SELECT article_json FROM pending_articles WHERE source_id=? "
                    "ORDER BY queued_at DESC, normalized_url DESC LIMIT ?",
                    (source.source_id, per_source if per_source else -1),
                ).fetchall()
                candidates.extend((Article(**json.loads(row[0])), source) for row in rows)
        return candidates

    def complete_pending(self, article):
        with self.lock:
            self.conn.execute(
                "DELETE FROM pending_articles WHERE normalized_url=?",
                (article.normalized_url,),
            )
            self.conn.commit()

    def reserve_delivery(
        self,
        article,
        title,
        body,
        discovered_at,
        daily_limit,
        country_daily_limit=0,
        country_source_daily_limit=0,
    ):
        digest = title_hash(title)
        body_digest = body_prefix_hash(body)
        published = parse_iso(article.published_at) or parse_iso(discovered_at) or utc_now()
        published_day = published.date().isoformat()
        accepted_day = (parse_iso(discovered_at) or utc_now()).date().isoformat()
        with self.lock:
            if self.conn.execute(
                "SELECT 1 FROM accepted_title_hashes WHERE title_hash=?",
                (digest,),
            ).fetchone():
                return False, "EXACT_TITLE_DUPLICATE"
            if body_digest and self.conn.execute(
                "SELECT 1 FROM accepted_body_hashes WHERE body_hash=?",
                (body_digest,),
            ).fetchone():
                return False, "BODY_HASH_DUPLICATE"
            accepted = self.conn.execute(
                """
                SELECT COUNT(*) FROM source_daily_accepts
                WHERE source_id=? AND published_day=?
                """,
                (article.source_id, published_day),
            ).fetchone()[0]
            # All collector limits use zero to mean unlimited.
            if daily_limit and accepted >= daily_limit:
                return False, f"SOURCE_DAILY_CAP_{daily_limit}"

            country_accepted, source_accepted = self.conn.execute(
                "SELECT COUNT(*), COALESCE(SUM(source_id=?), 0) "
                "FROM country_daily_accepts WHERE country=? AND accepted_day=?",
                (article.source_id, article.country, accepted_day),
            ).fetchone()
            if country_daily_limit and country_accepted >= country_daily_limit:
                return False, f"COUNTRY_DAILY_CAP_{country_daily_limit}"
            if country_source_daily_limit and source_accepted >= country_source_daily_limit:
                return False, f"COUNTRY_SOURCE_DAILY_CAP_{country_source_daily_limit}"

            accepted_at = iso(utc_now())
            try:
                self.conn.execute(
                    """
                    INSERT INTO accepted_title_hashes(
                        title_hash, normalized_url, source_id, accepted_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (digest, article.normalized_url, article.source_id, accepted_at),
                )
                self.conn.execute(
                    """
                    INSERT INTO accepted_body_hashes(
                        body_hash, normalized_url, source_id, accepted_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        body_digest,
                        article.normalized_url,
                        article.source_id,
                        accepted_at,
                    ),
                )
                self.conn.execute(
                    """
                    INSERT INTO source_daily_accepts(
                        normalized_url, source_id, published_day, accepted_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        article.normalized_url,
                        article.source_id,
                        published_day,
                        accepted_at,
                    ),
                )
                self.conn.execute(
                    "INSERT INTO country_daily_accepts VALUES (?, ?, ?, ?)",
                    (article.normalized_url, article.country, article.source_id, accepted_day),
                )
                self.conn.commit()
                return True, ""
            except sqlite3.IntegrityError:
                self.conn.rollback()
                return False, "QUALITY_RESERVATION_DUPLICATE"

    def save_article(self, article, fetched, discovered_at):
        with self.lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO articles(
                    normalized_url, source_id, source_name, country, original_url,
                    published_at, published_at_estimated, published_at_source,
                    section, section_source,
                    discovered_at, discovery_type, endpoint_url,
                    fetch_success, http_status, body_length,
                    fetch_elapsed_ms, fetch_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article.normalized_url, article.source_id, article.source_name,
                    article.country, article.url, article.published_at,
                    1 if article.published_at_estimated else 0,
                    article.published_at_source,
                    article.section,
                    article.section_source,
                    discovered_at, article.discovery_type, article.endpoint_url,
                    1 if fetched["success"] else 0,
                    fetched["http_status"], fetched["body_length"],
                    fetched["elapsed_ms"], fetched["error"],
                ),
            )
            self.conn.commit()

    def save_poll(self, row):
        with self.lock:
            self.conn.execute(
                """
                INSERT INTO poll_logs(
                    round_no, source_id, source_name, country, polled_at,
                    discovered_total, baseline_seeded_count, old_published_filtered,
                    new_article_count, rss_status, sitemap_status, latest_status,
                    elapsed_ms, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["round_no"], row["source_id"], row["source_name"], row["country"],
                    row["polled_at"], row["discovered_total"],
                    row["baseline_seeded_count"], row["old_published_filtered"],
                    row["new_article_count"], row["rss_status"],
                    row["sitemap_status"], row["latest_status"],
                    row["elapsed_ms"], row["error"],
                ),
            )
            self.conn.commit()

    def save_round_metrics(self, row):
        with self.lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO round_metrics(
                    round_no, session_id, started_at, ended_at,
                    queue_start_count, discovered_count, selected_count,
                    processed_count, accepted_count, dropped_stale,
                    dropped_overflow, queue_end_count,
                    queue_oldest_age_minutes, elapsed_ms
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["round_no"], row["session_id"], row["started_at"],
                    row["ended_at"], row["queue_start_count"],
                    row["discovered_count"], row["selected_count"],
                    row["processed_count"], row["accepted_count"],
                    row["dropped_stale"], row["dropped_overflow"],
                    row["queue_end_count"], row["queue_oldest_age_minutes"],
                    row["elapsed_ms"],
                ),
            )
            self.conn.commit()


def load_sources(path, include_review, excluded_countries=()):
    df = pd_read_csv(path)
    sources = []
    seen_ids = set()
    excluded_countries = set(excluded_countries)

    for _, r in df.iterrows():
        status = safe(r.get("ingestion_status")).upper()
        crawl_enabled = safe(r.get("crawl_enabled")).lower()
        if crawl_enabled and crawl_enabled != "true":
            continue
        if status != "ACTIVE" and not (include_review and status == "REVIEW"):
            continue

        rss_urls = split_urls(r.get("rss_urls"))
        if not rss_urls:
            rss_urls = split_urls(r.get("rss_url"))

        sitemap_urls = split_urls(r.get("news_sitemap_url"))

        latest_urls = split_urls(r.get("latest_page_urls"))
        if not latest_urls:
            latest_urls = split_urls(r.get("latest_page_url"))

        if not rss_urls and not sitemap_urls and not latest_urls:
            continue

        source_id = safe(r.get("source_id"))
        if not source_id:
            raise ValueError("Active registry row has an empty source_id.")
        if source_id in seen_ids:
            raise ValueError(f"Duplicate active source_id in registry: {source_id}")
        seen_ids.add(source_id)

        def int_value(name, default):
            try:
                return int(float(safe(r.get(name)) or default))
            except (TypeError, ValueError):
                return default

        def float_value(name, default):
            try:
                return float(safe(r.get(name)) or default)
            except (TypeError, ValueError):
                return default

        country = safe(r.get("country"))
        if country in excluded_countries:
            continue
        domain = safe(r.get("domain")).lower().removeprefix("www.")
        if not domain:
            raise ValueError(f"Active registry row has no domain: {source_id}")
        display_name = safe(r.get("source_name")) or domain
        source = Source(
            country=country,
            source_id=source_id,
            # source_name is a stable machine-facing identifier.  Human-facing
            # registry labels remain available internally as display_name.
            source_name=domain,
            domain=domain,
            homepage=safe(r.get("homepage")),
            rss_urls=rss_urls,
            sitemap_urls=sitemap_urls,
            latest_page_urls=latest_urls,
            article_url_regex=safe(r.get("article_url_regex")),
            body_selector=safe(r.get("body_selector")),
            ingestion_status=status,
            max_articles_per_day=max(1, int_value("max_articles_per_day", 300)),
            max_items_per_poll=max(0, int_value("max_items_per_poll", 0)),
            max_sitemap_urls_per_poll=max(
                0,
                int_value("max_sitemap_urls_per_poll", 0),
            ),
            domain_max_concurrency=max(
                1,
                int_value("domain_max_concurrency", 2),
            ),
            min_request_interval_seconds=max(
                0.0,
                float_value("min_request_interval_seconds", 1.5),
            ),
            domain_adapter=safe(r.get("domain_adapter")),
            display_name=display_name,
            timezone_name=(
                safe(r.get("timezone")) or timezone_for_country(country)
            ),
            coverage_focus=safe(r.get("coverage_focus")).upper(),
            domain_gate_required=safe(r.get("domain_gate_required")).lower() == "true",
        )
        if country_domain_mismatch(source):
            print(
                f"[REGISTRY SKIP] country/domain mismatch: "
                f"{source.source_id} {source.country} {source.domain}"
            )
            continue
        sources.append(source)

    return sources


def pd_read_csv(path):
    import pandas as pd
    return pd.read_csv(path, encoding="utf-8-sig")


def conditional_get(source, url, db, args):
    etag, last_modified = db.get_http_state(url)
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    try:
        r = source_get(
            source,
            args,
            url,
            headers=headers,
            timeout=args.timeout_seconds,
            allow_redirects=True,
        )
        db.save_http_state(
            url,
            r.headers.get("ETag") or etag,
            r.headers.get("Last-Modified") or last_modified,
            r.status_code,
        )
        return r, None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def parse_feed_endpoint(source, endpoint, db, args):
    db.ensure_endpoint(endpoint, source.source_id, "RSS")
    r, err = conditional_get(source, endpoint, db, args)

    if err:
        db.set_endpoint_error(endpoint, err)
        return [], None, err
    if r is None:
        return [], None, None
    if r.status_code == 304:
        return [], 304, None
    if r.status_code >= 400:
        err = f"HTTP {r.status_code}"
        db.set_endpoint_error(endpoint, err)
        return [], r.status_code, err

    feed = feedparser.parse(r.content)
    out = []
    item_limit = source.max_items_per_poll or args.max_feed_entries
    for e in feed.entries[:item_limit]:
        link = safe(e.get("link"))
        if not link or is_non_article_url(link):
            continue

        published = None
        published_source = ""
        # Parse the original timestamp before feedparser's struct_time so a
        # timezone-less KST/JST value is interpreted in the publisher's zone.
        for key in ("published", "updated", "created"):
            published = parse_quality_datetime(
                e.get(key),
                source.timezone_name,
            )
            if published:
                published_source = f"rss:{key}"
                break
        if not published:
            for key in ("published_parsed", "updated_parsed"):
                t = e.get(key)
                if t:
                    try:
                        published = datetime(
                            *t[:6],
                            tzinfo=timezone.utc,
                        ).isoformat()
                        published_source = f"rss:{key}"
                    except Exception:
                        pass
                    break

        categories = tuple(
            dict.fromkeys(
                safe(tag.get("term"))
                for tag in (e.get("tags") or [])
                if safe(tag.get("term"))
            )
        )

        out.append(Article(
            source_id=source.source_id,
            source_name=source.source_name,
            country=source.country,
            url=link,
            normalized_url=normalize_url(link),
            published_at=published,
            discovery_type="RSS",
            endpoint_url=endpoint,
            feed_title=safe(e.get("title")),
            feed_categories=categories,
            published_at_source=published_source,
        ))

    return out, r.status_code, None


def xml_bytes(resp):
    data = resp.content
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "gzip" in ctype or resp.url.lower().endswith(".gz"):
        try:
            return gzip.decompress(data)
        except Exception:
            return data
    return data


def local_tag(tag):
    return tag.split("}", 1)[-1].lower()


def extract_sitemap_records(data):
    # Some publishers put whitespace before the XML declaration. Trim only
    # the leading padding/BOM; keep strict XML parsing for the actual document.
    if isinstance(data, bytes):
        data = data.lstrip(b" \t\r\n")
        if data.startswith(b"\xef\xbb\xbf"):
            data = data[3:].lstrip(b" \t\r\n")
    else:
        data = data.lstrip("\ufeff \t\r\n")
    root = ET.fromstring(data)
    name = local_tag(root.tag)
    out = []

    if name == "urlset":
        for node in root:
            if local_tag(node.tag) != "url":
                continue
            namespace = node.tag.rsplit("}", 1)[0] + "}" if node.tag.startswith("{") else ""
            # The article URL is a direct sitemap <loc>, never image:loc or
            # video metadata, even when the extension appears first.
            loc_node = node.find(f"{namespace}loc")
            loc = safe(loc_node.text) if loc_node is not None else ""
            publication_date = next((
                safe(ch.text) for ch in node.iter()
                if local_tag(ch.tag) == "publication_date" and safe(ch.text)
            ), "")
            lastmod = node.find(f"{namespace}lastmod")
            date_value = publication_date or (safe(lastmod.text) if lastmod is not None else None)
            if loc and not is_non_article_url(loc):
                out.append(("url", loc, date_value))
        return out

    if name == "sitemapindex":
        for node in root:
            if local_tag(node.tag) != "sitemap":
                continue
            loc = None
            lastmod = None
            for ch in node:
                n = local_tag(ch.tag)
                if n == "loc":
                    loc = safe(ch.text)
                elif n == "lastmod":
                    lastmod = safe(ch.text)
            if loc:
                out.append(("index", loc, lastmod))
        return out

    raise ValueError(f"UNSUPPORTED_SITEMAP_ROOT: {name}")


def parse_sitemap_endpoint(source, endpoint, db, args):
    db.ensure_endpoint(endpoint, source.source_id, "SITEMAP")
    r, err = conditional_get(source, endpoint, db, args)
    if err:
        db.set_endpoint_error(endpoint, err)
        return [], None, err
    if r is None:
        return [], None, None
    if r.status_code == 304:
        return [], 304, None
    if r.status_code >= 400:
        err = f"HTTP {r.status_code}"
        db.set_endpoint_error(endpoint, err)
        return [], r.status_code, err

    try:
        records = extract_sitemap_records(xml_bytes(r))
    except Exception as e:
        err = f"SITEMAP_PARSE {type(e).__name__}: {e}"
        db.set_endpoint_error(endpoint, err)
        return [], r.status_code, err

    out = []

    def add_url(url, date_value, endpoint_url):
        published = parse_quality_datetime(date_value, source.timezone_name)
        out.append(Article(
            source_id=source.source_id,
            source_name=source.source_name,
            country=source.country,
            url=url,
            normalized_url=normalize_url(url),
            published_at=published,
            discovery_type="SITEMAP",
            endpoint_url=endpoint_url,
            published_at_source="sitemap" if published else "",
        ))

    if records and records[0][0] == "url":
        sitemap_limit = source.max_sitemap_urls_per_poll or args.max_sitemap_urls
        for _, url, date_value in records[:sitemap_limit]:
            add_url(url, date_value, endpoint)
        return out, r.status_code, None

    # index: children are treated as separate endpoints with their own baseline
    children = list(reversed(records))[:args.max_sitemap_children]
    errors = []

    for _, child_url, _ in children:
        db.ensure_endpoint(child_url, source.source_id, "SITEMAP")
        cr, cerr = conditional_get(source, child_url, db, args)
        if cerr:
            db.set_endpoint_error(child_url, cerr)
            errors.append(cerr)
            continue
        if cr is None or cr.status_code == 304:
            continue
        if cr.status_code >= 400:
            err = f"HTTP {cr.status_code}"
            db.set_endpoint_error(child_url, err)
            errors.append(err)
            continue
        try:
            child_records = extract_sitemap_records(xml_bytes(cr))
            sitemap_limit = source.max_sitemap_urls_per_poll or args.max_sitemap_urls
            for kind, url, date_value in child_records[:sitemap_limit]:
                if kind == "url":
                    add_url(url, date_value, child_url)
        except Exception as e:
            errors.append(f"{type(e).__name__}: {e}")

    return out, r.status_code, " | ".join(errors[:3]) if errors and not out else None


def robots_allowed(url, timeout):
    p = urlsplit(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"

    if robots_url not in ROBOTS_CACHE:
        rp = urllib.robotparser.RobotFileParser()
        rp.set_url(robots_url)
        status = "UNKNOWN"
        try:
            r = get_session().get(robots_url, timeout=timeout, allow_redirects=True)
            if r.status_code == 200:
                rp.parse(r.text.splitlines())
                status = "OK"
            else:
                rp.parse([])
                status = f"HTTP_{r.status_code}"
        except Exception as e:
            rp.parse([])
            status = f"UNKNOWN_{type(e).__name__}"
        ROBOTS_CACHE[robots_url] = (rp, status)

    rp, status = ROBOTS_CACHE[robots_url]
    if status == "OK":
        return rp.can_fetch(USER_AGENT, url), status
    return True, status


def looks_like_article(url, source):
    if not url.startswith(("http://", "https://")) or is_non_article_url(url):
        return False

    if source.article_url_regex:
        try:
            if not re.search(source.article_url_regex, url, re.I):
                return False
        except re.error:
            pass
    else:
        host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
        source_host = source.domain.lower().removeprefix("www.")
        if source_host and not (host == source_host or host.endswith("." + source_host)):
            return False

    path = (urlsplit(url).path or "").lower()
    if path in {"", "/"}:
        return False

    blocked = (
        "/tag/", "/tags/", "/category/", "/categories/",
        "/topic/", "/topics/", "/author/", "/authors/",
        "/search", "/privacy", "/terms", "/contact", "/about",
        "/subscribe", "/newsletter", "/podcast/",
    )
    return not any(x in path for x in blocked)


def parse_latest_endpoint(source, endpoint, db, args):
    db.ensure_endpoint(endpoint, source.source_id, "LATEST_PAGE")

    allowed, _ = robots_allowed(endpoint, args.timeout_seconds)
    if not allowed:
        err = "ROBOTS_DISALLOW"
        db.set_endpoint_error(endpoint, err)
        return [], None, err

    r, err = conditional_get(source, endpoint, db, args)
    if err:
        db.set_endpoint_error(endpoint, err)
        return [], None, err
    if r is None:
        return [], None, None
    if r.status_code == 304:
        return [], 304, None
    if r.status_code >= 400:
        err = f"HTTP {r.status_code}"
        db.set_endpoint_error(endpoint, err)
        return [], r.status_code, err

    soup = BeautifulSoup(r.text, "html.parser")
    out, seen = [], set()

    for a in soup.find_all("a", href=True):
        url = urljoin(r.url, a["href"])
        n = normalize_url(url)
        if not n or n in seen or not looks_like_article(url, source):
            continue
        seen.add(n)
        out.append(Article(
            source_id=source.source_id,
            source_name=source.source_name,
            country=source.country,
            url=url,
            normalized_url=n,
            published_at=None,
            discovery_type="LATEST_PAGE",
            endpoint_url=endpoint,
            feed_title=safe(a.get_text(" ", strip=True)),
        ))
        item_limit = source.max_items_per_poll or args.max_feed_entries
        if len(out) >= item_limit:
            break

    return out, r.status_code, None


def discover_source(source, db, args):
    started = time.perf_counter()
    items = []
    errors = []
    rss_status = []
    sitemap_status = []
    latest_status = []
    successful_endpoints = 0

    for endpoint in source.rss_urls:
        x, status, err = parse_feed_endpoint(source, endpoint, db, args)
        items += x
        rss_status.append(str(status))
        if err:
            errors.append(f"RSS:{err}")
        else:
            successful_endpoints += 1

    for endpoint in source.sitemap_urls:
        x, status, err = parse_sitemap_endpoint(source, endpoint, db, args)
        items += x
        sitemap_status.append(str(status))
        if err:
            errors.append(f"SITEMAP:{err}")
        else:
            successful_endpoints += 1

    for endpoint in source.latest_page_urls:
        x, status, err = parse_latest_endpoint(source, endpoint, db, args)
        items += x
        latest_status.append(str(status))
        if err:
            errors.append(f"LATEST:{err}")
        else:
            successful_endpoints += 1

    # dedupe only identical endpoint+normalized_url records first
    merged = {}
    for a in items:
        key = (a.endpoint_url, a.normalized_url)
        if a.normalized_url and key not in merged:
            merged[key] = a

    return {
        "source": source,
        "articles": list(merged.values()),
        "rss_status": ",".join(rss_status),
        "sitemap_status": ",".join(sitemap_status),
        "latest_status": ",".join(latest_status),
        "successful_endpoints": successful_endpoints,
        "error": " | ".join(errors[:8]),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }


def fetch_article(article, source, args):
    started = time.perf_counter()
    if is_non_article_url(article.url):
        return {
            "success": False, "http_status": None, "title": "", "body": "",
            "body_length": 0, "elapsed_ms": 0, "error": "NON_ARTICLE_URL",
        }
    def publisher_url_allowed(url):
        host = (urlsplit(url).hostname or "").lower().removeprefix("www.")
        return host == source.domain or host.endswith("." + source.domain)

    def domain_error(status=None):
        return {
            "success": False, "http_status": status, "title": "", "body": "",
            "body_length": 0, "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "error": "ARTICLE_PUBLISHER_DOMAIN_MISMATCH",
        }

    if source.domain_gate_required and not publisher_url_allowed(article.url):
        return domain_error()
    allowed, _ = robots_allowed(article.url, args.timeout_seconds)
    if not allowed:
        return {
            "success": False,
            "http_status": None,
            "title": "",
            "body": "",
            "body_length": 0,
            "elapsed_ms": 0,
            "error": "ROBOTS_DISALLOW",
        }

    try:
        r = source_get(
            source,
            args,
            article.url,
            timeout=args.timeout_seconds,
            allow_redirects=True,
            headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
        )
        if r.status_code >= 400:
            return {
                "success": False,
                "http_status": r.status_code,
                "title": "",
                "body": "",
                "body_length": 0,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "error": f"HTTP {r.status_code}",
            }

        if source.domain_gate_required and not publisher_url_allowed(r.url):
            return domain_error(r.status_code)

        content_type = safe(r.headers.get("Content-Type")).split(";", 1)[0].strip().lower()
        if (
            is_non_article_url(r.url)
            or content_type.startswith(("image/", "audio/", "video/"))
            or content_type == "application/pdf"
        ):
            return {
                "success": False, "http_status": r.status_code, "title": "", "body": "",
                "body_length": 0, "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "error": "NON_ARTICLE_CONTENT",
            }

        soup = BeautifulSoup(r.text, "html.parser")
        jsonld = read_jsonld(soup)
        article.title_suffix_aliases = extract_site_names(soup, jsonld)

        # Legacy Kafka/output fields remain intact; quality metadata is added
        # separately for downstream auditing and section pre-estimation.
        title = extract_quality_title(soup, jsonld, article.feed_title)
        body = extract_quality_body(r.text, r.url, source.body_selector)
        page_published_at, page_published_source = extract_published_at(
            soup,
            jsonld,
            default_timezone=source.timezone_name,
        )
        discovered_published_at = article.published_at
        discovered_published_source = article.published_at_source
        if page_published_at:
            article.published_at = page_published_at
            article.published_at_source = page_published_source
            article.published_at_estimated = False
        elif discovered_published_at:
            article.published_at = discovered_published_at
            article.published_at_source = (
                discovered_published_source or "discovery_endpoint"
            )
            article.published_at_estimated = False
        else:
            article.published_at = iso(utc_now())
            article.published_at_source = "collection_time_fallback"
            article.published_at_estimated = True

        # A bad upstream timezone must never put an article in the future.
        # Prefer the independently discovered feed/sitemap timestamp; if that
        # is also invalid or absent, use an explicitly flagged collection time.
        reference_time = utc_now()
        future_tolerance = timedelta(
            minutes=getattr(args, "published_future_tolerance_minutes", 10)
        )
        published_dt = parse_iso(article.published_at)
        if published_dt and published_dt > reference_time + future_tolerance:
            discovered_dt = parse_iso(discovered_published_at)
            if (
                discovered_dt
                and discovered_dt <= reference_time + future_tolerance
            ):
                article.published_at = iso(discovered_dt)
                article.published_at_source = (
                    discovered_published_source or "discovery_endpoint"
                ) + ":future_page_rejected"
                article.published_at_estimated = False
            else:
                article.published_at = iso(reference_time)
                article.published_at_source = "collection_time_future_guard"
                article.published_at_estimated = True

        section, section_source = extract_section(
            soup,
            jsonld,
            r.url,
            article.feed_categories,
        )
        if not section and source.coverage_focus in {
            "POLITICS",
            "ECONOMY",
            "SOCIETY",
            "TECHNOLOGY",
            "CULTURE",
            "SPORTS",
        }:
            section = source.coverage_focus
            section_source = "registry_coverage_focus"
        article.section = safe(section)
        article.section_source = safe(section_source)

        wall, wall_reason = is_wall_content(title, body)
        if not title:
            error = "TITLE_MISSING"
        elif wall:
            error = wall_reason
        elif len(body) < args.min_body_chars:
            error = f"BODY_TOO_SHORT({len(body)})"
        else:
            error = None
        success = error is None
        return {
            "success": success,
            "http_status": r.status_code,
            "title": title,
            "body": body,
            "body_length": len(body),
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "error": error,
        }

    except Exception as e:
        return {
            "success": False,
            "http_status": None,
            "title": "",
            "body": "",
            "body_length": 0,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "error": f"{type(e).__name__}: {e}",
        }


def seed_endpoint_baseline(db, endpoint_url, articles):
    inserted = 0
    for a in articles:
        if db.mark_seen(a, "ENDPOINT_BASELINE"):
            inserted += 1
    db.mark_endpoint_ready(endpoint_url)
    return inserted


def warmup_round(sources, db, args, attempt_no):
    print(f"\n[Warm-up attempt {attempt_no}/{args.warmup_retries}]")

    seeded_urls = 0
    newly_ready_endpoints = 0

    with ThreadPoolExecutor(max_workers=args.poll_workers) as pool:
        futures = {
            pool.submit(discover_source, s, db, args): s
            for s in sources
        }

        for future in as_completed(futures):
            result = future.result()
            by_endpoint = {}

            for a in result["articles"]:
                by_endpoint.setdefault(a.endpoint_url, []).append(a)

            for endpoint, arts in by_endpoint.items():
                if not db.endpoint_ready(endpoint):
                    seeded_urls += seed_endpoint_baseline(db, endpoint, arts)
                    newly_ready_endpoints += 1

    print(
        f"  newly ready endpoints={newly_ready_endpoints:,} | "
        f"baseline URLs inserted={seeded_urls:,}"
    )


def all_endpoints(sources):
    out = []
    for s in sources:
        for x in s.rss_urls:
            out.append((x, s.source_id, "RSS"))
        for x in s.sitemap_urls:
            out.append((x, s.source_id, "SITEMAP"))
        for x in s.latest_page_urls:
            out.append((x, s.source_id, "LATEST_PAGE"))
    return out


def initialize_endpoints(sources, db):
    for endpoint, source_id, dtype in all_endpoints(sources):
        db.ensure_endpoint(endpoint, source_id, dtype)


def count_ready_endpoints(db):
    with db.lock:
        total = db.conn.execute("SELECT COUNT(*) FROM endpoint_baseline").fetchone()[0]
        ready = db.conn.execute(
            "SELECT COUNT(*) FROM endpoint_baseline WHERE baseline_ready=1"
        ).fetchone()[0]
    return ready, total



def final_baseline_refresh(sources, db, args):
    """
    CRITICAL:
    Immediately before experiment_start, poll every source once more and
    mark every currently visible article as seen.

    Why:
    Warm-up retry #1 may baseline an endpoint successfully.
    During retry #2/#3, new articles can appear before experiment_start.
    Without this final refresh, those articles could be counted in Round 1.

    This refresh never emits a new article. It only updates the baseline.
    Endpoints that fail here remain safe: their first later success is still
    handled as baseline-only by poll_round().
    """
    print("\n[Final Baseline Refresh]")
    print("Seeding all currently visible URLs immediately before experiment start.")

    total_seen_inserted = 0
    baseline_endpoints_completed = 0
    failed_sources = 0

    with ThreadPoolExecutor(max_workers=args.poll_workers) as pool:
        futures = {
            pool.submit(discover_source, s, db, args): s
            for s in sources
        }

        for future in as_completed(futures):
            source = futures[future]
            try:
                result = future.result()
            except Exception as e:
                failed_sources += 1
                print(
                    f"  [WARN] {source.country} / {source.source_name}: "
                    f"{type(e).__name__}: {e}"
                )
                continue

            # Every article visible NOW becomes baseline, even if the endpoint
            # was already baseline_ready during an earlier warm-up attempt.
            endpoint_groups = {}
            for article in result["articles"]:
                endpoint_groups.setdefault(article.endpoint_url, []).append(article)

            for endpoint, articles in endpoint_groups.items():
                inserted_here = 0
                for article in articles:
                    if db.mark_seen(article, "FINAL_BASELINE_REFRESH"):
                        inserted_here += 1

                total_seen_inserted += inserted_here

                # If this endpoint was not ready before but succeeded now,
                # it is safe to mark it ready after seeding all visible URLs.
                if not db.endpoint_ready(endpoint):
                    db.mark_endpoint_ready(endpoint)
                    baseline_endpoints_completed += 1

    ready, total = count_ready_endpoints(db)

    print(
        f"  newly inserted baseline URLs={total_seen_inserted:,} | "
        f"newly completed endpoints={baseline_endpoints_completed:,} | "
        f"failed sources={failed_sources:,}"
    )
    print(f"  endpoint baseline ready after final refresh: {ready:,}/{total:,}")
    print("[Final Baseline Refresh complete]\n")



def poll_round(
    round_no,
    sources,
    db,
    args,
    experiment_start,
    kafka_producer,
    session_id=None,
):
    print(f"\n[Round {round_no}] {utc_now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    round_started = time.monotonic()
    round_started_at = utc_now()
    queue_start = db.pending_snapshot(round_started_at)
    configured_sources = list(sources)
    pollable_sources, quarantined = db.pollable_sources(configured_sources)
    if quarantined:
        print(
            f"  circuit breaker skipped   : {len(quarantined):,} source(s)"
        )
    poll_sources = fair_sources(
        pollable_sources,
        round_no,
        getattr(args, "max_sources_per_country_per_round", 0),
    )

    with ThreadPoolExecutor(max_workers=args.poll_workers) as pool:
        futures = {
            pool.submit(discover_source, s, db, args): s
            for s in poll_sources
        }
        results = []
        for future in as_completed(futures):
            try:
                results.append(future.result())
            except Exception as e:
                s = futures[future]
                results.append({
                    "source": s,
                    "articles": [],
                    "rss_status": "",
                    "sitemap_status": "",
                    "latest_status": "",
                    "successful_endpoints": 0,
                    "error": f"{type(e).__name__}: {e}",
                    "elapsed_ms": 0,
                })

    for result in results:
        full_source_failure = (
            bool(safe(result["error"]))
            and result.get("successful_endpoints", 0) == 0
        )
        consecutive, quarantined_until = db.record_poll_health(
            result["source"].source_id,
            full_source_failure,
            result["error"],
            getattr(args, "poll_error_quarantine_threshold", 0),
            getattr(args, "poll_error_quarantine_minutes", 0),
        )
        if (
            full_source_failure
            and quarantined_until
            and consecutive == getattr(args, "poll_error_quarantine_threshold", 0)
        ):
            print(
                f"  [QUARANTINE] {result['source'].country} / "
                f"{result['source'].source_name} until {iso(quarantined_until)}"
            )

    new_articles = []
    source_new = Counter()
    baseline_seeded = 0
    old_filtered = 0

    guard_cutoff = experiment_start - timedelta(minutes=args.published_tolerance_minutes)

    for result in results:
        source = result["source"]
        endpoint_groups = {}

        for a in result["articles"]:
            endpoint_groups.setdefault(a.endpoint_url, []).append(a)

        for endpoint, arts in endpoint_groups.items():
            if not db.endpoint_ready(endpoint):
                # CRITICAL FIX:
                # first success after failed warm-up is baseline only
                baseline_seeded += seed_endpoint_baseline(db, endpoint, arts)
                continue

            for a in arts:
                published_dt = parse_iso(a.published_at)
                if published_dt and published_dt < guard_cutoff:
                    if db.mark_seen(a, "OLD_PUBLISHED_FILTER"):
                        old_filtered += 1
                    continue

                if db.enqueue_article(a):
                    new_articles.append((a, source))
                    source_new[source.source_id] += 1

    discovered_count = len(new_articles)
    new_articles = fair_articles(
        db.pending_for_sources(
            configured_sources,
            getattr(args, "max_fetches_per_source_per_round", 0),
            getattr(args, "pending_max_age_minutes", 1440),
            getattr(args, "max_pending_per_source", 0),
        ),
        configured_sources, round_no,
        getattr(args, "max_fetches_per_country_per_round", 0),
        getattr(args, "max_fetches_per_source_per_round", 0),
    )
    pruned = getattr(db, "last_pending_pruned", {})
    if pruned.get("stale") or pruned.get("overflow"):
        print(
            "  pending queue pruned       : "
            f"stale={pruned.get('stale', 0):,}, "
            f"overflow={pruned.get('overflow', 0):,}"
        )

    discovered_at = iso(utc_now())

    fetch_results = {}
    kafka_queued = 0
    if new_articles:
        with ThreadPoolExecutor(max_workers=args.fetch_workers) as pool:
            futures = {
                pool.submit(fetch_article, article, source, args): (article, source)
                for article, source in new_articles
            }
            # Accept in country/publisher order even when faster publishers
            # finish first, so duplicates and caps do not favor response speed.
            for future, (article, source) in futures.items():
                try:
                    fetched = future.result()
                except Exception as exc:
                    fetched = {
                        "success": False, "http_status": None, "title": "",
                        "body": "", "body_length": 0, "elapsed_ms": 0,
                        "error": f"{type(exc).__name__}: {exc}",
                    }

                if fetched.get("title"):
                    fetched["title"] = db.clean_title_suffix(
                        source,
                        fetched["title"],
                        args.title_suffix_min_occurrences,
                        article.title_suffix_aliases,
                    )

                quality_status = "PASS"
                quality_reasons = []
                if fetched.get("http_status") == 200:
                    quality_status, quality_reasons = db.record_quality_sample(
                        article,
                        fetched,
                        args.quality_min_source_sample,
                    )

                # Latest pages often have no discovery timestamp.  Once the
                # article page supplies one, apply the same old-article guard
                # that RSS/sitemap candidates already passed through.
                published_dt = parse_iso(article.published_at)
                if (
                    fetched["success"]
                    and published_dt
                    and published_dt < guard_cutoff
                ):
                    fetched["success"] = False
                    fetched["error"] = "OLD_PUBLISHED_AFTER_FETCH"
                    old_filtered += 1

                if fetched["success"] and not has_long_line(fetched["body"]):
                    fetched["success"] = False
                    fetched["error"] = "NO_BODY_LINE_OVER_40_CHARS"

                if fetched["success"] and country_domain_mismatch(source):
                    fetched["success"] = False
                    fetched["error"] = "COUNTRY_DOMAIN_MISMATCH"

                if fetched["success"] and quality_status == "QUARANTINE":
                    fetched["success"] = False
                    fetched["error"] = "SOURCE_QUALITY_GATE:" + "|".join(
                        quality_reasons
                    )

                # Reserve both the cross-publisher title and the source/day
                # capacity in one transaction immediately before delivery.
                if fetched["success"]:
                    allowed, reason = db.reserve_delivery(
                        article,
                        fetched["title"],
                        fetched["body"],
                        discovered_at,
                        source_daily_limit_for_profile(
                            getattr(args, "collection_profile", "legacy5"),
                            source.max_articles_per_day,
                        ),
                        getattr(args, "max_articles_per_country_per_day", 0),
                        getattr(args, "max_articles_per_source_country_day", 0),
                    )
                    if not allowed:
                        fetched["success"] = False
                        fetched["error"] = reason

                fetch_results[article.normalized_url] = fetched
                db.save_article(article, fetched, discovered_at)
                # Only articles with a valid extracted body enter news.raw.v1.
                if (
                    fetched["success"]
                    and not getattr(args, "observe_only", False)
                    and kafka_producer is not None
                    and kafka_producer.publish(
                        build_raw_article_event(article, fetched, discovered_at)
                    )
                ):
                    kafka_queued += 1
                db.complete_pending(article)

    if kafka_queued:
        stats = kafka_producer.flush_round()
        print(
            f"  Kafka queued/published     : {kafka_queued:,}/"
            f"{stats['delivered']:,} -> {kafka_producer.topic}"
        )
        if stats["failed"] or stats["remaining"]:
            print(
                f"  Kafka delivery warning     : failed={stats['failed']}, "
                f"pending={stats['remaining']}"
            )

    source_result_map = {r["source"].source_id: r for r in results}

    for source in poll_sources:
        r = source_result_map.get(source.source_id, {
            "articles": [], "rss_status": "", "sitemap_status": "",
            "latest_status": "", "elapsed_ms": 0, "error": "",
        })
        db.save_poll({
            "round_no": round_no,
            "source_id": source.source_id,
            "source_name": source.source_name,
            "country": source.country,
            "polled_at": discovered_at,
            "discovered_total": len(r["articles"]),
            "baseline_seeded_count": 0,
            "old_published_filtered": 0,
            "new_article_count": source_new[source.source_id],
            "rss_status": r["rss_status"],
            "sitemap_status": r["sitemap_status"],
            "latest_status": r["latest_status"],
            "elapsed_ms": r["elapsed_ms"],
            "error": r["error"],
        })

    success = sum(1 for x in fetch_results.values() if x["success"])
    round_ended_at = utc_now()
    elapsed_seconds = time.monotonic() - round_started
    queue_end = db.pending_snapshot(round_ended_at)
    db.save_round_metrics({
        "round_no": round_no,
        "session_id": session_id or iso(experiment_start),
        "started_at": iso(round_started_at),
        "ended_at": iso(round_ended_at),
        "queue_start_count": queue_start["count"],
        "discovered_count": discovered_count,
        "selected_count": len(new_articles),
        "processed_count": len(fetch_results),
        "accepted_count": success,
        "dropped_stale": int(pruned.get("stale", 0)),
        "dropped_overflow": int(pruned.get("overflow", 0)),
        "queue_end_count": queue_end["count"],
        "queue_oldest_age_minutes": queue_end["oldest_age_minutes"],
        "elapsed_ms": int(elapsed_seconds * 1000),
    })
    print(
        f"  new={len(new_articles):,} | body_success={success:,} | "
        f"body_fail={len(new_articles)-success:,} | "
        f"late_baseline_seeded={baseline_seeded:,} | "
        f"old_published_filtered={old_filtered:,}"
    )
    print(
        "  pending queue             : "
        f"{queue_start['count']:,} -> {queue_end['count']:,} "
        f"(oldest={queue_end['oldest_age_minutes']:.1f}m)"
    )

    by_country = Counter(a.country for a, _ in new_articles)
    if by_country:
        print("  top countries: " + ", ".join(
            f"{k}={v}" for k, v in by_country.most_common(8)
        ))

    if source_new:
        source_names = {s.source_id: s for s in configured_sources}
        print("  top sources: " + ", ".join(
            f"{source_names[sid].source_name}={cnt}"
            for sid, cnt in source_new.most_common(8)
        ))

    return discovered_count, elapsed_seconds


def export_csvs(db, output_dir):
    with db.lock:
        article_rows = db.conn.execute(
            """
            SELECT source_id, source_name, country, original_url, published_at,
                   published_at_estimated, published_at_source,
                   section, section_source,
                   discovered_at, discovery_type, endpoint_url, fetch_success,
                   http_status, body_length, fetch_elapsed_ms, fetch_error
            FROM articles
            ORDER BY discovered_at
            """
        ).fetchall()

        poll_rows = db.conn.execute(
            """
            SELECT round_no, source_id, source_name, country, polled_at,
                   discovered_total, baseline_seeded_count, old_published_filtered,
                   new_article_count, rss_status, sitemap_status, latest_status,
                   elapsed_ms, error
            FROM poll_logs
            ORDER BY id
            """
        ).fetchall()

        endpoint_rows = db.conn.execute(
            """
            SELECT endpoint_url, source_id, discovery_type, baseline_ready,
                   baseline_seeded_at, last_error
            FROM endpoint_baseline
            ORDER BY source_id, endpoint_url
            """
        ).fetchall()

    def write(name, headers, rows):
        with (output_dir / name).open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(headers)
            w.writerows(rows)

    write(
        "articles.csv",
        ["source_id","source_name","country","article_url","published_at",
         "published_at_estimated","published_at_source","section","section_source",
         "discovered_at","discovery_type","endpoint_url","fetch_success",
         "http_status","body_length","fetch_elapsed_ms","fetch_error"],
        article_rows,
    )
    write(
        "poll_logs.csv",
        ["round_no","source_id","source_name","country","polled_at",
         "discovered_total","baseline_seeded_count","old_published_filtered",
         "new_article_count","rss_status","sitemap_status","latest_status",
         "elapsed_ms","error"],
        poll_rows,
    )
    write(
        "endpoint_baseline.csv",
        ["endpoint_url","source_id","discovery_type","baseline_ready",
         "baseline_seeded_at","last_error"],
        endpoint_rows,
    )


def build_summary(
    db,
    sources,
    started_at,
    ended_at,
    required_window_hours=24.0,
    active_runtime_seconds=None,
    session_id=None,
    pending_max_age_minutes=None,
    startup_queue_metrics=None,
):
    wall_clock_seconds = max((ended_at - started_at).total_seconds(), 1)
    elapsed_seconds = max(
        active_runtime_seconds
        if active_runtime_seconds is not None
        else wall_clock_seconds,
        1,
    )
    elapsed_hours = elapsed_seconds / 3600
    with db.lock:
        total = db.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]
        success = db.conn.execute(
            "SELECT COUNT(*) FROM articles WHERE fetch_success=1"
        ).fetchone()[0]
        country = db.conn.execute(
            "SELECT country, COUNT(*) FROM articles GROUP BY country ORDER BY COUNT(*) DESC"
        ).fetchall()
        source = db.conn.execute(
            "SELECT source_name, country, COUNT(*) FROM articles GROUP BY source_id ORDER BY COUNT(*) DESC LIMIT 30"
        ).fetchall()
        rounds = db.conn.execute(
            "SELECT round_no, SUM(new_article_count) FROM poll_logs GROUP BY round_no ORDER BY round_no"
        ).fetchall()
        round_queue_metrics = {
            row[0]: row[1:] for row in db.conn.execute(
                "SELECT round_no, session_id, queue_start_count, "
                "discovered_count, selected_count, processed_count, "
                "accepted_count, dropped_stale, dropped_overflow, "
                "queue_end_count, queue_oldest_age_minutes, elapsed_ms "
                "FROM round_metrics ORDER BY round_no"
            ).fetchall()
        }
        errors = db.conn.execute(
            "SELECT COUNT(*) FROM poll_logs WHERE error IS NOT NULL AND TRIM(error)<>''"
        ).fetchone()[0]
        polls = db.conn.execute("SELECT COUNT(*) FROM poll_logs").fetchone()[0]
        body = db.conn.execute(
            "SELECT COALESCE(AVG(body_length),0), COALESCE(AVG(fetch_elapsed_ms),0) FROM articles"
        ).fetchone()
        successful_countries = dict(db.conn.execute(
            "SELECT country, COUNT(*) FROM articles WHERE fetch_success=1 GROUP BY country"
        ).fetchall())
        successful_sources = db.conn.execute(
            "SELECT country, source_id, COUNT(*) FROM articles WHERE fetch_success=1 "
            "GROUP BY country, source_id"
        ).fetchall()
        pending_count = db.conn.execute("SELECT COUNT(*) FROM pending_articles").fetchone()[0]
        pending_oldest = db.conn.execute(
            "SELECT MIN(queued_at) FROM pending_articles"
        ).fetchone()[0]
        outcome_rows = db.conn.execute(
            "SELECT fetch_success, fetch_error, COUNT(*) FROM articles "
            "GROUP BY fetch_success, fetch_error"
        ).fetchall()
        source_outcome_rows = db.conn.execute(
            "SELECT source_id, fetch_success, fetch_error, COUNT(*) "
            "FROM articles GROUP BY source_id, fetch_success, fetch_error"
        ).fetchall()
        poll_health = {
            row[0]: row[1:] for row in db.conn.execute(
                "SELECT source_id, consecutive_errors, total_errors, "
                "last_error, quarantined_until FROM source_poll_health"
            ).fetchall()
        }
        pending_drop_meta = dict(db.conn.execute(
            "SELECT key, value FROM run_meta WHERE key IN "
            "('pending_dropped_stale', 'pending_dropped_overflow')"
        ).fetchall())
        source_articles = {
            row[0]: row[1:] for row in db.conn.execute(
                "SELECT source_id, COUNT(*), SUM(fetch_success), AVG(fetch_elapsed_ms) "
                "FROM articles GROUP BY source_id"
            ).fetchall()
        }
        source_polls = {
            row[0]: row[1:] for row in db.conn.execute(
                "SELECT source_id, COUNT(*), "
                "SUM(CASE WHEN TRIM(COALESCE(error,''))<>'' THEN 1 ELSE 0 END), "
                "MAX(polled_at) FROM poll_logs GROUP BY source_id"
            ).fetchall()
        }
        last_errors = dict(db.conn.execute(
            "SELECT p.source_id, p.error FROM poll_logs p "
            "JOIN (SELECT source_id, MAX(id) AS last_id FROM poll_logs GROUP BY source_id) x "
            "ON p.id=x.last_id"
        ).fetchall())
        session_queue_totals = (
            db.conn.execute(
                "SELECT COALESCE(SUM(discovered_count),0), "
                "COALESCE(SUM(processed_count),0), "
                "COALESCE(SUM(dropped_stale),0), "
                "COALESCE(SUM(dropped_overflow),0) "
                "FROM round_metrics WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if session_id else (0, 0, 0, 0)
        )

    ready_ep, total_ep = count_ready_endpoints(db)
    article_outcomes = Counter()
    for fetch_success, error, count in outcome_rows:
        article_outcomes[classify_article_outcome(bool(fetch_success), error)] += count
    for name in (
        "accepted", "filtered", "quality_rejected",
        "access_failed", "processing_failed",
    ):
        article_outcomes.setdefault(name, 0)
    source_outcomes = defaultdict(Counter)
    source_failure_reasons = defaultdict(Counter)
    for source_id, fetch_success, error, count in source_outcome_rows:
        outcome = classify_article_outcome(bool(fetch_success), error)
        source_outcomes[source_id][outcome] += count
        if not fetch_success:
            source_failure_reasons[source_id][
                summarize_failure_reason(error)
            ] += count
    eligible_attempts = total - article_outcomes["filtered"]
    pending_oldest_dt = parse_iso(pending_oldest)
    pending_oldest_age_minutes = (
        max((ended_at - pending_oldest_dt).total_seconds() / 60, 0)
        if pending_oldest_dt else 0
    )
    quarantined_source_ids = {
        source_id
        for source_id, (_consecutive, _total_errors, _error, until) in poll_health.items()
        if parse_iso(until) and parse_iso(until) > ended_at
    }
    source_coverage = []
    for configured in sources:
        attempted, accepted, latency = source_articles.get(configured.source_id, (0, 0, 0))
        outcome_counts = source_outcomes[configured.source_id]
        failure_reasons = source_failure_reasons[configured.source_id]
        poll_count, poll_errors, last_polled = source_polls.get(configured.source_id, (0, 0, None))
        consecutive_errors, total_poll_errors, health_error, quarantined_until = (
            poll_health.get(configured.source_id, (0, 0, "", None))
        )
        source_coverage.append({
            "country": configured.country,
            "source_id": configured.source_id,
            "source_name": configured.source_name,
            "polls": poll_count,
            "poll_errors": poll_errors,
            "last_polled_at": last_polled,
            "last_poll_error": last_errors.get(configured.source_id) or "",
            "consecutive_poll_errors": consecutive_errors,
            "total_full_source_failures": total_poll_errors,
            "quarantined_until": quarantined_until or "",
            "attempted_articles": attempted,
            "successful_articles": accepted,
            "article_success_rate_pct": round(accepted / attempted * 100, 2) if attempted else None,
            "filtered_articles": outcome_counts["filtered"],
            "quality_rejected_articles": outcome_counts["quality_rejected"],
            "access_failed_articles": outcome_counts["access_failed"],
            "processing_failed_articles": outcome_counts["processing_failed"],
            "dominant_failure_reason": (
                failure_reasons.most_common(1)[0][0]
                if failure_reasons else ""
            ),
            "average_fetch_latency_ms": round(latency or 0, 1) if attempted else None,
            "status": (
                "NOT_POLLED" if not poll_count else
                "QUARANTINED" if configured.source_id in quarantined_source_ids else
                "POLL_ERROR" if last_errors.get(configured.source_id) else
                "ARTICLES_ACCEPTED" if accepted else
                "ARTICLE_CHECK_FAILED" if attempted else
                "NO_NEW_ARTICLES"
            ),
        })

    country_coverage = [
        {
            "country": name,
            "configured_sources": sum(s.country == name for s in sources),
            "successful_articles": successful_countries.get(name, 0),
            "contributing_sources": sum(
                c == name for c, _, _ in successful_sources
            ),
            "largest_source_share": round(
                max(
                    (n for c, _, n in successful_sources if c == name),
                    default=0,
                ) / successful_countries.get(name, 1),
                4,
            ),
            "polled_sources": sum(
                row["polls"] > 0
                for row in source_coverage if row["country"] == name
            ),
            "polls": sum(
                row["polls"]
                for row in source_coverage if row["country"] == name
            ),
            "poll_errors": sum(
                row["poll_errors"]
                for row in source_coverage if row["country"] == name
            ),
            "attempted_articles": sum(
                row["attempted_articles"]
                for row in source_coverage if row["country"] == name
            ),
            "article_success_rate_pct": (
                round(
                    successful_countries.get(name, 0) / sum(
                        row["attempted_articles"]
                        for row in source_coverage
                        if row["country"] == name
                    ) * 100,
                    2,
                )
                if any(
                    row["attempted_articles"]
                    for row in source_coverage if row["country"] == name
                ) else None
            ),
        }
        for name in sorted({s.country for s in sources})
    ]
    country_coverage_alerts = []
    for row in country_coverage:
        reasons = []
        if not row["successful_articles"]:
            reasons.append("NO_ACCEPTED_ARTICLES")
        if row["contributing_sources"] < 3:
            reasons.append("FEWER_THAN_3_CONTRIBUTING_SOURCES")
        if row["largest_source_share"] > 0.50:
            reasons.append("LARGEST_SOURCE_SHARE_GT_50_PERCENT")
        if reasons:
            country_coverage_alerts.append({
                "country": row["country"],
                "reasons": reasons,
            })

    by_round = []
    for round_no, new_article_count in rounds:
        metrics = round_queue_metrics.get(round_no)
        row = {
            "round_no": round_no,
            "new_articles": new_article_count or 0,
        }
        if metrics:
            (
                metric_session_id,
                queue_start_count,
                discovered_count,
                selected_count,
                processed_count,
                accepted_count,
                dropped_stale,
                dropped_overflow,
                queue_end_count,
                queue_oldest_age_minutes,
                elapsed_ms,
            ) = metrics
            row.update({
                "session_id": metric_session_id,
                "queue_start_count": queue_start_count,
                "discovered_count": discovered_count,
                "selected_count": selected_count,
                "processed_count": processed_count,
                "accepted_count": accepted_count,
                "dropped_stale": dropped_stale,
                "dropped_overflow": dropped_overflow,
                "queue_end_count": queue_end_count,
                "queue_oldest_age_minutes": round(
                    queue_oldest_age_minutes or 0, 1
                ),
                "elapsed_ms": elapsed_ms,
            })
        by_round.append(row)

    startup_queue_metrics = startup_queue_metrics or {
        "before_count": pending_count,
        "after_count": pending_count,
        "stale": 0,
        "overflow": 0,
        "oldest_age_minutes": pending_oldest_age_minutes,
    }
    session_discovered, session_processed, session_stale, session_overflow = (
        session_queue_totals
    )
    session_stale += int(startup_queue_metrics.get("stale", 0))
    session_overflow += int(startup_queue_metrics.get("overflow", 0))

    return {
        "collection_mode": db.get_meta("collection_mode") or "publish",
        "collection_profile": db.get_meta("collection_profile") or "legacy5",
        "experiment_started_at_utc": iso(started_at),
        "experiment_ended_at_utc": iso(ended_at),
        "elapsed_hours": elapsed_hours,
        "wall_clock_hours": wall_clock_seconds / 3600,
        "required_window_hours": required_window_hours,
        "window_complete": elapsed_hours >= required_window_hours,
        "remaining_window_hours": round(
            max(required_window_hours - elapsed_hours, 0),
            3,
        ),
        "sources": len(sources),
        "countries": len({s.country for s in sources}),
        "pending_fetches": pending_count,
        "pending_oldest_age_minutes": round(pending_oldest_age_minutes, 1),
        "pending_dropped_stale": int(pending_drop_meta.get("pending_dropped_stale", 0)),
        "pending_dropped_overflow": int(pending_drop_meta.get("pending_dropped_overflow", 0)),
        "pending_dropped_stale_session": int(session_stale),
        "pending_dropped_overflow_session": int(session_overflow),
        "pending_discovered_session": int(session_discovered),
        "pending_processed_session": int(session_processed),
        "pending_max_age_minutes_configured": pending_max_age_minutes,
        "pending_age_limit_exceeded": bool(
            pending_max_age_minutes
            and pending_oldest_age_minutes > pending_max_age_minutes
        ),
        "startup_queue_cleanup": startup_queue_metrics,
        "quarantined_sources": len(quarantined_source_ids),
        "source_coverage": source_coverage,
        "country_coverage": country_coverage,
        "country_coverage_alerts": country_coverage_alerts,
        "endpoints_ready": ready_ep,
        "endpoints_total": total_ep,
        "new_articles": total,
        "fetch_success": success,
        "fetch_success_rate_pct": round(success / total * 100, 2) if total else 0,
        "article_outcomes": dict(article_outcomes),
        "eligible_article_success_rate_pct": (
            round(success / eligible_attempts * 100, 2)
            if eligible_attempts else 0
        ),
        "articles_per_hour": round(total / (elapsed_seconds / 3600), 2),
        "articles_per_minute": round(total / (elapsed_seconds / 60), 2),
        "peak_per_round": max((x[1] or 0 for x in rounds), default=0),
        "poll_error_rate_pct": round(errors / polls * 100, 2) if polls else 0,
        "average_body_chars": round(body[0], 1),
        "average_fetch_latency_ms": round(body[1], 1),
        "by_country": [{"country": c, "articles": n} for c, n in country],
        "top_sources": [{"source_name": n, "country": c, "articles": k} for n, c, k in source],
        "by_round": by_round,
    }


def write_summary(summary_path, summary):
    """Refresh readable reports alongside the full collection summary."""
    import csv

    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for filename, key in (
        ("country_status.csv", "country_coverage"),
        ("source_status.csv", "source_coverage"),
    ):
        rows = summary[key]
        if rows:
            with (summary_path.parent / filename).open("w", encoding="utf-8-sig", newline="") as output:
                writer = csv.DictWriter(output, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)


def print_summary(s):
    print("\n" + "=" * 100)
    print("24H COLLECTION PoC v3 RESULT")
    print("=" * 100)
    print(f"Sources                    : {s['sources']:,}")
    print(f"Collection mode            : {s['collection_mode']}")
    print(f"Endpoints ready            : {s['endpoints_ready']:,}/{s['endpoints_total']:,}")
    print(f"New articles               : {s['new_articles']:,}")
    print(f"Fetch success rate         : {s['fetch_success_rate_pct']:.2f}%")
    print(
        f"Eligible success rate      : "
        f"{s['eligible_article_success_rate_pct']:.2f}%"
    )
    print(
        "Article outcomes           : "
        + ", ".join(f"{k}={v:,}" for k, v in s["article_outcomes"].items())
    )
    print(
        f"Pending queue              : {s['pending_fetches']:,} "
        f"(oldest={s['pending_oldest_age_minutes']:.1f}m, "
        f"dropped stale={s['pending_dropped_stale']:,}, "
        f"overflow={s['pending_dropped_overflow']:,})"
    )
    print(
        "Pending this session       : "
        f"discovered={s['pending_discovered_session']:,}, "
        f"processed={s['pending_processed_session']:,}, "
        f"stale={s['pending_dropped_stale_session']:,}, "
        f"overflow={s['pending_dropped_overflow_session']:,}"
    )
    if s["pending_age_limit_exceeded"]:
        print(
            "Pending queue warning     : oldest item exceeds configured "
            f"{s['pending_max_age_minutes_configured']} minute limit"
        )
    print(f"Quarantined sources        : {s['quarantined_sources']:,}")
    print(f"Articles / hour            : {s['articles_per_hour']:.2f}")
    print(f"Articles / minute          : {s['articles_per_minute']:.2f}")
    print(f"Peak per polling round     : {s['peak_per_round']:,}")
    print(f"Poll error rate            : {s['poll_error_rate_pct']:.2f}%")
    print(f"Required window complete   : {s['window_complete']}")
    print("\n[Country]")
    for row in s["country_coverage"]:
        rate = row["article_success_rate_pct"]
        print(
            f"  {row['country']:<20} accepted={row['successful_articles']:>6,} "
            f"sources={row['contributing_sources']}/{row['configured_sources']} "
            f"article_success={'N/A' if rate is None else str(rate) + '%'} "
            f"poll_errors={row['poll_errors']}/{row['polls']}"
        )


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--collection-profile",
        choices=COLLECTION_PROFILES,
        default=os.getenv("COLLECTOR_PROFILE", "legacy5"),
        help="legacy5 uses registry.csv; global47 uses registry_50country.csv "
        "without China, Egypt, and Norway",
    )
    ap.add_argument(
        "--exclude-country",
        action="append",
        default=[],
        help="Country name to exclude; repeat for multiple countries",
    )
    ap.add_argument(
        "--registry",
        default=os.getenv("COLLECTOR_REGISTRY_PATH") or None,
    )
    ap.add_argument("--output-dir", default="output2")
    ap.add_argument(
        "--observe-only", action="store_true",
        help="Collect and report locally without Kafka; use an isolated observe subdirectory",
    )
    ap.add_argument("--duration-hours", type=float, default=24.0)
    ap.add_argument("--duration-minutes", type=float)
    ap.add_argument(
        "--run-forever",
        action="store_true",
        help="Run continuously until the process receives a stop signal",
    )
    ap.add_argument("--poll-seconds", type=int, default=300)
    ap.add_argument("--poll-workers", type=int, default=20)
    ap.add_argument("--fetch-workers", type=int, default=16)
    ap.add_argument("--max-sources-per-country-per-round", type=int)
    ap.add_argument("--max-fetches-per-country-per-round", type=int)
    ap.add_argument("--max-fetches-per-source-per-round", type=int)
    ap.add_argument("--max-articles-per-country-per-day", type=int)
    ap.add_argument("--max-articles-per-source-country-day", type=int)
    ap.add_argument("--pending-max-age-minutes", type=int)
    ap.add_argument("--max-pending-per-source", type=int)
    ap.add_argument("--poll-error-quarantine-threshold", type=int)
    ap.add_argument("--poll-error-quarantine-minutes", type=int)
    ap.add_argument("--timeout-seconds", type=int, default=12)
    ap.add_argument("--max-feed-entries", type=int, default=200)
    ap.add_argument("--max-sitemap-urls", type=int, default=500)
    ap.add_argument("--max-sitemap-children", type=int, default=12)
    ap.add_argument("--min-body-chars", type=int, default=300)
    ap.add_argument("--warmup-retries", type=int, default=3)
    ap.add_argument("--warmup-retry-sleep", type=int, default=10)
    ap.add_argument("--published-tolerance-minutes", type=int, default=10)
    ap.add_argument("--published-future-tolerance-minutes", type=int, default=10)
    ap.add_argument("--quality-min-source-sample", type=int, default=10)
    ap.add_argument("--title-suffix-min-occurrences", type=int, default=5)
    ap.add_argument("--required-window-hours", type=float, default=24.0)
    ap.add_argument("--include-review", action="store_true")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument(
        "--kafka-bootstrap",
        default=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"),
        help="Kafka bootstrap servers (local host default: localhost:9092)",
    )
    ap.add_argument(
        "--kafka-topic",
        default=os.getenv("KAFKA_RAW_TOPIC", "news.raw.v1"),
        help="Raw article Kafka topic",
    )
    args = ap.parse_args()
    if args.registry is None:
        args.registry = str(Path(__file__).with_name(
            "registry_50country.csv"
            if args.observe_only or args.collection_profile == "global47"
            else "registry.csv"
        ))
    args.exclude_countries = sorted(
        PROFILE_EXCLUDED_COUNTRIES[args.collection_profile]
        | {safe(country) for country in args.exclude_country if safe(country)}
    )
    if args.required_window_hours <= 0:
        ap.error("--required-window-hours must be greater than zero")
    if args.title_suffix_min_occurrences <= 0:
        ap.error("--title-suffix-min-occurrences must be greater than zero")
    observe_limits = {
        "max_sources_per_country_per_round": 10,
        "max_fetches_per_country_per_round": 10,
        "max_fetches_per_source_per_round": 3,
        "max_articles_per_country_per_day": 1000,
        "max_articles_per_source_country_day": 150,
    }
    expanded_profile = args.observe_only or args.collection_profile == "global47"
    volume_limit_names = {
        "max_articles_per_country_per_day",
        "max_articles_per_source_country_day",
    }
    for name, observe_default in observe_limits.items():
        if getattr(args, name) is None:
            # Keep the existing five-country collector uncapped by new budgets.
            default = observe_default if expanded_profile else 0
            if args.collection_profile == "global47" and name in volume_limit_names:
                default = 0
            setattr(args, name, default)
        if getattr(args, name) < 0:
            ap.error(f"--{name.replace('_', '-')} must be zero or greater")
    reliability_defaults = {
        "pending_max_age_minutes": (120, 1440),
        "max_pending_per_source": (100, 0),
        "poll_error_quarantine_threshold": (6, 0),
        "poll_error_quarantine_minutes": (360, 0),
    }
    for name, (observe_default, publish_default) in reliability_defaults.items():
        if getattr(args, name) is None:
            setattr(
                args,
                name,
                observe_default if expanded_profile else publish_default,
            )
        if getattr(args, name) < 0:
            ap.error(f"--{name.replace('_', '-')} must be zero or greater")
    if bool(args.poll_error_quarantine_threshold) != bool(
        args.poll_error_quarantine_minutes
    ):
        ap.error(
            "--poll-error-quarantine-threshold and "
            "--poll-error-quarantine-minutes must both be zero or positive"
        )
    return args


def main():
    args = parse_args()
    registry = Path(args.registry)
    out = Path(args.output_dir)
    if args.observe_only:
        out = out / "observe"
    out.mkdir(parents=True, exist_ok=True)

    health_path = (
        out / "collector.heartbeat" if args.observe_only else Path(
            os.getenv("COLLECTOR_HEALTH_FILE", str(out / "collector.heartbeat"))
        )
    )
    health_path.parent.mkdir(parents=True, exist_ok=True)
    health_path.unlink(missing_ok=True)

    db_path = out / "collection_24h_v2.db"
    summary_path = out / "summary.json"
    kafka_failed_path = out / "kafka_failed.jsonl"

    if args.reset:
        for p in [db_path, summary_path, kafka_failed_path, out / "articles.csv", out / "poll_logs.csv", out / "endpoint_baseline.csv", out / "country_status.csv", out / "source_status.csv"]:
            if p.exists():
                p.unlink()

    sources = load_sources(
        registry,
        args.include_review,
        args.exclude_countries,
    )
    if not sources:
        raise RuntimeError("No sources loaded from registry.")
    if args.collection_profile == "global47":
        countries = {source.country for source in sources}
        if len(countries) != 47:
            raise RuntimeError(
                "global47 profile must load exactly 47 countries; "
                f"loaded {len(countries)}"
            )
    args.domain_limiter = DomainLimiter(sources)

    print("=" * 100)
    print("Collector v1 - RAW ARTICLE COLLECTION")
    print("=" * 100)
    print(f"Registry        : {registry}")
    print(f"Profile         : {args.collection_profile}")
    print(
        "Excluded        : "
        f"{', '.join(args.exclude_countries) if args.exclude_countries else 'none'}"
    )
    print(f"Output          : {out.resolve()}")
    print(f"Sources         : {len(sources)}")
    print(f"Poll interval   : {args.poll_seconds}s")
    print(f"Run mode        : {'FOREVER' if args.run_forever else 'BOUNDED'}")
    print(f"Warmup retries  : {args.warmup_retries}")
    print(f"Published guard : {args.published_tolerance_minutes} min")
    print(f"Pending max age : {args.pending_max_age_minutes} min")
    print(f"Pending/source  : {args.max_pending_per_source or 'unlimited'}")
    print(
        "Poll quarantine : "
        f"{args.poll_error_quarantine_threshold or 'disabled'} consecutive / "
        f"{args.poll_error_quarantine_minutes or 0} min"
    )
    print(f"Required window : {args.required_window_hours:g}h")
    kafka_producer = None
    if args.observe_only:
        print("Delivery        : OBSERVE ONLY (Kafka disabled)")
    else:
        print(f"Kafka bootstrap : {args.kafka_bootstrap}")
        print(f"Kafka topic     : {args.kafka_topic}")
        kafka_producer = KafkaRawProducer(
            args.kafka_bootstrap, args.kafka_topic, kafka_failed_path,
        )
        print("Kafka connection: OK")

    db = DB(db_path)
    process_session_id = iso(utc_now())
    startup_queue_metrics = None

    try:
        db.set_meta("collection_mode", "observe" if args.observe_only else "publish")
        db.set_meta("collection_profile", args.collection_profile)
        initialize_endpoints(sources, db)
        removed_state = db.prune_inactive_source_state(sources)
        if any(removed_state.values()):
            print(
                "Removed-source state pruned: "
                + ", ".join(
                    f"{name}={count:,}"
                    for name, count in removed_state.items()
                )
            )
        startup_queue_metrics = db.prune_pending_queue(
            sources,
            args.pending_max_age_minutes,
            args.max_pending_per_source,
        )
        print(
            "Startup pending cleanup: "
            f"{startup_queue_metrics['before_count']:,} -> "
            f"{startup_queue_metrics['after_count']:,} "
            f"(stale={startup_queue_metrics['stale']:,}, "
            f"overflow={startup_queue_metrics['overflow']:,}, "
            f"oldest={startup_queue_metrics['oldest_age_minutes']:.1f}m)"
        )

        # Warm-up retries. Endpoints that still fail are NOT dangerous:
        # their first later success will baseline-seed and emit zero new articles.
        #
        # IMPORTANT:
        # Final Baseline Refresh is executed only for a NEW experiment.
        # On resume, we must NOT baseline currently visible articles again,
        # because they may be legitimate articles published while the program was down.
        existing_start = db.get_meta("experiment_started_at_utc")

        if existing_start:
            started_at = parse_iso(existing_start)
            print(
                "\n[Resume mode] Existing experiment start found. "
                "Warm-up / Final Baseline Refresh skipped."
            )
        else:
            startup_sources = fair_sources(
                sources, 1, args.max_sources_per_country_per_round
            )
            if db.get_meta("warmup_complete") != "1":
                for attempt in range(1, args.warmup_retries + 1):
                    warmup_round(startup_sources, db, args, attempt)
                    ready, total = count_ready_endpoints(db)
                    print(f"  endpoint baseline ready: {ready}/{total}")
                    if ready == total:
                        break
                    if attempt < args.warmup_retries:
                        time.sleep(args.warmup_retry_sleep)

                db.set_meta("warmup_complete", "1")
                db.set_meta("warmup_completed_at_utc", iso(utc_now()))

            # CRITICAL FIX:
            # Refresh ALL currently visible URLs immediately before experiment start.
            # Remaining publishers initialize lazily on their first poll. The
            # existing baseline-only guard prevents a historical article dump.
            final_baseline_refresh(startup_sources, db, args)

            # Experiment clock starts AFTER the final baseline snapshot.
            started_at = utc_now()
            db.set_meta("experiment_started_at_utc", iso(started_at))
            db.set_meta("final_baseline_completed_at_utc", iso(started_at))
            db.set_meta("active_runtime_seconds", "0")

        # Readiness is reported only after endpoint initialization and baseline
        # preparation have completed successfully.
        health_path.write_text(
            json.dumps({
                "collection_mode": "observe" if args.observe_only else "publish",
                "collection_profile": args.collection_profile,
            }),
            encoding="utf-8",
        )
        try:
            prior_active_runtime = float(
                db.get_meta("active_runtime_seconds") or 0
            )
        except (TypeError, ValueError):
            prior_active_runtime = 0.0
        session_started_at = utc_now()
        write_summary(summary_path, build_summary(
            db, sources, started_at, session_started_at,
            args.required_window_hours, prior_active_runtime,
            session_id=process_session_id,
            pending_max_age_minutes=args.pending_max_age_minutes,
            startup_queue_metrics=startup_queue_metrics,
        ))

        def active_runtime_seconds():
            return prior_active_runtime + max(
                (utc_now() - session_started_at).total_seconds(),
                0,
            )

        if args.run_forever:
            deadline = None
        else:
            duration_seconds = (
                args.duration_minutes * 60
                if args.duration_minutes is not None
                else args.duration_hours * 3600
            )
            remaining_runtime = max(
                duration_seconds - prior_active_runtime,
                0,
            )
            deadline = session_started_at + timedelta(
                seconds=remaining_runtime
            )

        with db.lock:
            r = db.conn.execute("SELECT COALESCE(MAX(round_no),0) FROM poll_logs").fetchone()
            round_no = int(r[0]) + 1

        while deadline is None or utc_now() < deadline:
            health_path.touch()
            _, elapsed = poll_round(
                round_no, sources, db, args, started_at, kafka_producer,
                session_id=process_session_id,
            )
            export_csvs(db, out)
            snapshot_ended_at = utc_now()
            active_seconds = active_runtime_seconds()
            db.set_meta("active_runtime_seconds", str(active_seconds))
            summary = build_summary(
                db,
                sources,
                started_at,
                snapshot_ended_at,
                args.required_window_hours,
                active_seconds,
                session_id=process_session_id,
                pending_max_age_minutes=args.pending_max_age_minutes,
                startup_queue_metrics=startup_queue_metrics,
            )
            write_summary(summary_path, summary)
            health_path.touch()
            round_no += 1

            if deadline is None:
                sleep_for = max(args.poll_seconds - elapsed, 0)
            else:
                remaining = (deadline - utc_now()).total_seconds()
                if remaining <= 0:
                    break
                sleep_for = min(max(args.poll_seconds - elapsed, 0), remaining)

            if sleep_for > 0:
                print(f"  sleeping {sleep_for:.1f}s...")
                time.sleep(sleep_for)

        if deadline is not None:
            ended_at = utc_now()
            active_seconds = active_runtime_seconds()
            db.set_meta("active_runtime_seconds", str(active_seconds))
            summary = build_summary(
                db,
                sources,
                started_at,
                ended_at,
                args.required_window_hours,
                active_seconds,
                session_id=process_session_id,
                pending_max_age_minutes=args.pending_max_age_minutes,
                startup_queue_metrics=startup_queue_metrics,
            )
            write_summary(summary_path, summary)
            export_csvs(db, out)
            print_summary(summary)

    except KeyboardInterrupt:
        print("\nInterrupted. Run again WITHOUT --reset to resume.")
        if "started_at" in locals():
            interrupted_at = utc_now()
            active_seconds = active_runtime_seconds()
            db.set_meta("active_runtime_seconds", str(active_seconds))
            summary = build_summary(
                db,
                sources,
                started_at,
                interrupted_at,
                args.required_window_hours,
                active_seconds,
                session_id=process_session_id,
                pending_max_age_minutes=args.pending_max_age_minutes,
                startup_queue_metrics=startup_queue_metrics,
            )
            write_summary(summary_path, summary)
            if not summary["window_complete"]:
                print(
                    "Collection window is incomplete: "
                    f"{summary['elapsed_hours']:.2f}/"
                    f"{summary['required_window_hours']:.2f} hours."
                )
    finally:
        try:
            if kafka_producer is not None:
                kafka_producer.close()
        except Exception:
            pass
        db.close()


if __name__ == "__main__":
    main()
