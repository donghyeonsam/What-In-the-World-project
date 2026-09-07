#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
PoC 2 v3

Fixes:
- RSS / Sitemap / Latest Page supported.
- Endpoint-level baseline seeding.
- If an endpoint fails warm-up, its first later success is BASELINE ONLY.
  It can never dump old URLs as "new" merely because warm-up failed.
- published_at guard rejects articles clearly older than experiment start.
- source-level new article counts printed each round.
- final baseline refresh immediately before experiment_start.
- resume mode skips baseline refresh so downtime articles are not lost.
- SQLite state makes restart safe.
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
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

import feedparser
import requests
import trafilatura
from bs4 import BeautifulSoup

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

    # Prefer metadata intended for article/social previews.
    candidates = [
        ("meta", {"property": "og:title"}, "content"),
        ("meta", {"name": "twitter:title"}, "content"),
        ("meta", {"property": "twitter:title"}, "content"),
    ]
    for tag_name, attrs, value_attr in candidates:
        node = soup.find(tag_name, attrs=attrs)
        if node:
            value = safe(node.get(value_attr))
            if value:
                return value

    # Then prefer the page's main heading.
    h1 = soup.find("h1")
    if h1:
        value = safe(h1.get_text(" ", strip=True))
        if value:
            return value

    # Last fallback: HTML <title>.
    if soup.title:
        value = safe(soup.title.get_text(" ", strip=True))
        if value:
            return value

    return ""


def build_raw_article_event(article, fetched, discovered_at):
    """Build the exact collector payload used by news.raw.v1."""
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
        s = requests.Session()
        s.headers.update({
            "User-Agent": USER_AGENT,
            "Accept": "*/*",
            "Accept-Encoding": "gzip, deflate",
        })
        THREAD_LOCAL.session = s
    return s


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

CREATE TABLE IF NOT EXISTS articles (
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
"""


class DB:
    def __init__(self, path):
        self.conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self.conn.executescript(SCHEMA)
        self.conn.commit()
        self.lock = threading.Lock()

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

    def save_article(self, article, fetched, discovered_at):
        with self.lock:
            self.conn.execute(
                """
                INSERT OR REPLACE INTO articles(
                    normalized_url, source_id, source_name, country, original_url,
                    published_at, discovered_at, discovery_type, endpoint_url,
                    fetch_success, http_status, body_length,
                    fetch_elapsed_ms, fetch_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    article.normalized_url, article.source_id, article.source_name,
                    article.country, article.url, article.published_at,
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


def load_sources(path, include_review):
    df = pd_read_csv(path)
    sources = []

    for _, r in df.iterrows():
        status = safe(r.get("ingestion_status")).upper()
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

        sources.append(Source(
            country=safe(r.get("country")),
            source_id=safe(r.get("source_id")),
            source_name=safe(r.get("source_name")),
            domain=safe(r.get("domain")),
            homepage=safe(r.get("homepage")),
            rss_urls=rss_urls,
            sitemap_urls=sitemap_urls,
            latest_page_urls=latest_urls,
            article_url_regex=safe(r.get("article_url_regex")),
            body_selector=safe(r.get("body_selector")),
            ingestion_status=status,
        ))

    unique = {s.source_id: s for s in sources}
    return list(unique.values())


def pd_read_csv(path):
    import pandas as pd
    return pd.read_csv(path, encoding="utf-8-sig")


def conditional_get(url, db, timeout):
    etag, last_modified = db.get_http_state(url)
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    try:
        r = get_session().get(
            url,
            headers=headers,
            timeout=timeout,
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
    r, err = conditional_get(endpoint, db, args.timeout_seconds)

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
    for e in feed.entries[:args.max_feed_entries]:
        link = safe(e.get("link"))
        if not link:
            continue

        published = None
        for key in ("published_parsed", "updated_parsed"):
            t = e.get(key)
            if t:
                try:
                    published = datetime(*t[:6], tzinfo=timezone.utc).isoformat()
                except Exception:
                    pass
                break

        out.append(Article(
            source_id=source.source_id,
            source_name=source.source_name,
            country=source.country,
            url=link,
            normalized_url=normalize_url(link),
            published_at=published,
            discovery_type="RSS",
            endpoint_url=endpoint,
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
    root = ET.fromstring(data)
    name = local_tag(root.tag)
    out = []

    if name == "urlset":
        for node in root:
            if local_tag(node.tag) != "url":
                continue
            loc = None
            date_value = None
            for ch in node.iter():
                n = local_tag(ch.tag)
                if n == "loc" and loc is None:
                    loc = safe(ch.text)
                elif n in {"publication_date", "lastmod"} and not date_value:
                    date_value = safe(ch.text)
            if loc:
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

    return out


def parse_sitemap_endpoint(source, endpoint, db, args):
    db.ensure_endpoint(endpoint, source.source_id, "SITEMAP")
    r, err = conditional_get(endpoint, db, args.timeout_seconds)
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
        out.append(Article(
            source_id=source.source_id,
            source_name=source.source_name,
            country=source.country,
            url=url,
            normalized_url=normalize_url(url),
            published_at=parse_iso(date_value).isoformat() if parse_iso(date_value) else None,
            discovery_type="SITEMAP",
            endpoint_url=endpoint_url,
        ))

    if records and records[0][0] == "url":
        for _, url, date_value in records[:args.max_sitemap_urls]:
            add_url(url, date_value, endpoint)
        return out, r.status_code, None

    # index: children are treated as separate endpoints with their own baseline
    children = list(reversed(records))[:args.max_sitemap_children]
    errors = []

    for _, child_url, _ in children:
        db.ensure_endpoint(child_url, source.source_id, "SITEMAP")
        cr, cerr = conditional_get(child_url, db, args.timeout_seconds)
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
            for kind, url, date_value in child_records[:args.max_sitemap_urls]:
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
    if not url.startswith(("http://", "https://")):
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

    r, err = conditional_get(endpoint, db, args.timeout_seconds)
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
        ))
        if len(out) >= args.max_feed_entries:
            break

    return out, r.status_code, None


def discover_source(source, db, args):
    started = time.perf_counter()
    items = []
    errors = []
    rss_status = []
    sitemap_status = []
    latest_status = []

    for endpoint in source.rss_urls:
        x, status, err = parse_feed_endpoint(source, endpoint, db, args)
        items += x
        rss_status.append(str(status))
        if err:
            errors.append(f"RSS:{err}")

    for endpoint in source.sitemap_urls:
        x, status, err = parse_sitemap_endpoint(source, endpoint, db, args)
        items += x
        sitemap_status.append(str(status))
        if err:
            errors.append(f"SITEMAP:{err}")

    for endpoint in source.latest_page_urls:
        x, status, err = parse_latest_endpoint(source, endpoint, db, args)
        items += x
        latest_status.append(str(status))
        if err:
            errors.append(f"LATEST:{err}")

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
        "error": " | ".join(errors[:8]),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }


def fetch_article(article, source, args):
    started = time.perf_counter()
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
        r = get_session().get(
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

        # Title is extracted independently so sitemap-discovered articles also have it.
        title = extract_article_title(r.text)

        # Primary extraction: Trafilatura.
        body = (trafilatura.extract(
            r.text,
            url=r.url,
            include_comments=False,
            include_tables=False,
        ) or "").strip()

        # Fallback extraction when Trafilatura returns too little text.
        if len(body) < args.min_body_chars:
            soup = BeautifulSoup(r.text, "html.parser")
            for x in soup(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
                x.decompose()

            selectors = []
            if source.body_selector:
                selectors.append(source.body_selector)
            selectors += [
                '[itemprop="articleBody"]', 'article', 'main article',
                '.article-body', '.story-body', '.entry-content', 'main'
            ]

            best = body
            for sel in selectors:
                try:
                    for node in soup.select(sel):
                        text = "\n".join(
                            p.get_text(" ", strip=True)
                            for p in node.find_all("p")
                            if len(p.get_text(" ", strip=True)) >= 25
                        ).strip()
                        if len(text) > len(best):
                            best = text
                except Exception:
                    pass
            body = best

        success = len(body) >= args.min_body_chars
        return {
            "success": success,
            "http_status": r.status_code,
            "title": title,
            "body": body,
            "body_length": len(body),
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "error": None if success else f"BODY_TOO_SHORT({len(body)})",
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



def poll_round(round_no, sources, db, args, experiment_start, kafka_producer):
    print(f"\n[Round {round_no}] {utc_now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')}")
    round_started = time.monotonic()

    with ThreadPoolExecutor(max_workers=args.poll_workers) as pool:
        futures = {
            pool.submit(discover_source, s, db, args): s
            for s in sources
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
                    "error": f"{type(e).__name__}: {e}",
                    "elapsed_ms": 0,
                })

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

                if db.mark_seen(a, "NEW_DISCOVERY"):
                    new_articles.append((a, source))
                    source_new[source.source_id] += 1

    discovered_at = iso(utc_now())

    fetch_results = {}
    kafka_queued = 0
    if new_articles:
        with ThreadPoolExecutor(max_workers=args.fetch_workers) as pool:
            futures = {
                pool.submit(fetch_article, article, source, args): (article, source)
                for article, source in new_articles
            }
            for future in as_completed(futures):
                article, source = futures[future]
                fetched = future.result()
                fetch_results[article.normalized_url] = fetched
                db.save_article(article, fetched, discovered_at)
                raw_event = build_raw_article_event(article, fetched, discovered_at)
                # Only articles with a valid extracted body enter news.raw.v1.
                if fetched["success"] and kafka_producer.publish(raw_event):
                    kafka_queued += 1

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

    for source in sources:
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
    print(
        f"  new={len(new_articles):,} | body_success={success:,} | "
        f"body_fail={len(new_articles)-success:,} | "
        f"late_baseline_seeded={baseline_seeded:,} | "
        f"old_published_filtered={old_filtered:,}"
    )

    by_country = Counter(a.country for a, _ in new_articles)
    if by_country:
        print("  top countries: " + ", ".join(
            f"{k}={v}" for k, v in by_country.most_common(8)
        ))

    if source_new:
        source_names = {s.source_id: s for s in sources}
        print("  top sources: " + ", ".join(
            f"{source_names[sid].source_name}={cnt}"
            for sid, cnt in source_new.most_common(8)
        ))

    return len(new_articles), time.monotonic() - round_started


def export_csvs(db, output_dir):
    with db.lock:
        article_rows = db.conn.execute(
            """
            SELECT source_id, source_name, country, original_url, published_at,
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


def build_summary(db, sources, started_at, ended_at):
    elapsed_seconds = max((ended_at - started_at).total_seconds(), 1)
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
        errors = db.conn.execute(
            "SELECT COUNT(*) FROM poll_logs WHERE error IS NOT NULL AND TRIM(error)<>''"
        ).fetchone()[0]
        polls = db.conn.execute("SELECT COUNT(*) FROM poll_logs").fetchone()[0]
        body = db.conn.execute(
            "SELECT COALESCE(AVG(body_length),0), COALESCE(AVG(fetch_elapsed_ms),0) FROM articles"
        ).fetchone()

    ready_ep, total_ep = count_ready_endpoints(db)

    return {
        "experiment_started_at_utc": iso(started_at),
        "experiment_ended_at_utc": iso(ended_at),
        "elapsed_hours": elapsed_seconds / 3600,
        "sources": len(sources),
        "endpoints_ready": ready_ep,
        "endpoints_total": total_ep,
        "new_articles": total,
        "fetch_success": success,
        "fetch_success_rate_pct": round(success / total * 100, 2) if total else 0,
        "articles_per_hour": round(total / (elapsed_seconds / 3600), 2),
        "articles_per_minute": round(total / (elapsed_seconds / 60), 2),
        "peak_per_round": max((x[1] or 0 for x in rounds), default=0),
        "poll_error_rate_pct": round(errors / polls * 100, 2) if polls else 0,
        "average_body_chars": round(body[0], 1),
        "average_fetch_latency_ms": round(body[1], 1),
        "by_country": [{"country": c, "articles": n} for c, n in country],
        "top_sources": [{"source_name": n, "country": c, "articles": k} for n, c, k in source],
        "by_round": [{"round_no": r, "new_articles": n} for r, n in rounds],
    }


def print_summary(s):
    print("\n" + "=" * 100)
    print("24H COLLECTION PoC v3 RESULT")
    print("=" * 100)
    print(f"Sources                    : {s['sources']:,}")
    print(f"Endpoints ready            : {s['endpoints_ready']:,}/{s['endpoints_total']:,}")
    print(f"New articles               : {s['new_articles']:,}")
    print(f"Fetch success rate         : {s['fetch_success_rate_pct']:.2f}%")
    print(f"Articles / hour            : {s['articles_per_hour']:.2f}")
    print(f"Articles / minute          : {s['articles_per_minute']:.2f}")
    print(f"Peak per polling round     : {s['peak_per_round']:,}")
    print(f"Poll error rate            : {s['poll_error_rate_pct']:.2f}%")
    print("\n[Country]")
    for row in s["by_country"]:
        print(f"  {row['country']:<20} {row['articles']:>8,}")


def parse_args():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", default="output1_5/merged_pre24h_source_registry_v2.csv")
    ap.add_argument("--output-dir", default="output2")
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
    ap.add_argument("--timeout-seconds", type=int, default=12)
    ap.add_argument("--max-feed-entries", type=int, default=200)
    ap.add_argument("--max-sitemap-urls", type=int, default=500)
    ap.add_argument("--max-sitemap-children", type=int, default=12)
    ap.add_argument("--min-body-chars", type=int, default=300)
    ap.add_argument("--warmup-retries", type=int, default=3)
    ap.add_argument("--warmup-retry-sleep", type=int, default=10)
    ap.add_argument("--published-tolerance-minutes", type=int, default=10)
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
    return ap.parse_args()


def main():
    args = parse_args()
    registry = Path(args.registry)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    health_path = Path(
        os.getenv("COLLECTOR_HEALTH_FILE", str(out / "collector.heartbeat"))
    )
    health_path.parent.mkdir(parents=True, exist_ok=True)
    health_path.unlink(missing_ok=True)

    db_path = out / "collection_24h_v2.db"
    summary_path = out / "summary.json"
    kafka_failed_path = out / "kafka_failed.jsonl"

    if args.reset:
        for p in [db_path, summary_path, kafka_failed_path, out / "articles.csv", out / "poll_logs.csv", out / "endpoint_baseline.csv"]:
            if p.exists():
                p.unlink()

    sources = load_sources(registry, args.include_review)
    if not sources:
        raise RuntimeError("No sources loaded from registry.")

    print("=" * 100)
    print("Collector v1 - RAW ARTICLE COLLECTION")
    print("=" * 100)
    print(f"Registry        : {registry}")
    print(f"Output          : {out.resolve()}")
    print(f"Sources         : {len(sources)}")
    print(f"Poll interval   : {args.poll_seconds}s")
    print(f"Run mode        : {'FOREVER' if args.run_forever else 'BOUNDED'}")
    print(f"Warmup retries  : {args.warmup_retries}")
    print(f"Published guard : {args.published_tolerance_minutes} min")
    print(f"Kafka bootstrap : {args.kafka_bootstrap}")
    print(f"Kafka topic     : {args.kafka_topic}")

    kafka_producer = KafkaRawProducer(
        args.kafka_bootstrap,
        args.kafka_topic,
        kafka_failed_path,
    )
    print("Kafka connection: OK")

    db = DB(db_path)

    try:
        initialize_endpoints(sources, db)

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
            if db.get_meta("warmup_complete") != "1":
                for attempt in range(1, args.warmup_retries + 1):
                    warmup_round(sources, db, args, attempt)
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
            final_baseline_refresh(sources, db, args)

            # Experiment clock starts AFTER the final baseline snapshot.
            started_at = utc_now()
            db.set_meta("experiment_started_at_utc", iso(started_at))
            db.set_meta("final_baseline_completed_at_utc", iso(started_at))

        # Readiness is reported only after endpoint initialization and baseline
        # preparation have completed successfully.
        health_path.touch()

        if args.run_forever:
            deadline = None
        else:
            duration_seconds = (
                args.duration_minutes * 60
                if args.duration_minutes is not None
                else args.duration_hours * 3600
            )
            deadline = started_at + timedelta(seconds=duration_seconds)

        with db.lock:
            r = db.conn.execute("SELECT COALESCE(MAX(round_no),0) FROM poll_logs").fetchone()
            round_no = int(r[0]) + 1

        while deadline is None or utc_now() < deadline:
            health_path.touch()
            _, elapsed = poll_round(
                round_no, sources, db, args, started_at, kafka_producer
            )
            export_csvs(db, out)
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
            ended_at = min(utc_now(), deadline)
            summary = build_summary(db, sources, started_at, ended_at)
            summary_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            export_csvs(db, out)
            print_summary(summary)

    except KeyboardInterrupt:
        print("\nInterrupted. Run again WITHOUT --reset to resume.")
    finally:
        try:
            kafka_producer.close()
        except Exception:
            pass
        db.close()


if __name__ == "__main__":
    main()
