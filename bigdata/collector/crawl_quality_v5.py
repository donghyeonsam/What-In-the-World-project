#!/usr/bin/env python3
"""Shared extraction and quality checks for the v5 news crawler.

The functions in this module are deliberately independent from the long-running
collector so they can also be applied to an existing JSONL collection.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlsplit

from bs4 import BeautifulSoup
import trafilatura


COUNTRY_ISO3 = {
    "Germany": "DEU",
    "Japan": "JPN",
    "South Korea": "KOR",
    "United Kingdom": "GBR",
    "United States": "USA",
}

WALL_TITLE_PATTERNS = (
    "willkommen auf golem.de",
    "access denied",
    "just a moment",
    "attention required",
    "cookie consent",
    "consent required",
)

WALL_BODY_PATTERNS = (
    "besuchen sie golem.de wie gewohnt mit werbung",
    "bitte stimmen sie der verwendung von cookies zu",
    "enable javascript and cookies to continue",
    "we value your privacy",
    "access to this page has been denied",
)

GENERIC_SECTIONS = {"news", "latest", "article", "articles", "index", "www", "html"}

LATIN_STOPWORDS = {
    "about", "after", "again", "against", "also", "been", "before", "being",
    "between", "could", "from", "have", "into", "more", "news", "over", "said",
    "that", "their", "there", "these", "they", "this", "through", "under", "were",
    "what", "when", "where", "which", "while", "with", "would", "your",
    "aber", "auch", "dass", "eine", "einer", "eines", "für", "gegen", "haben",
    "nach", "nicht", "oder", "sein", "sich", "über", "unter", "werden", "wird",
}


def safe(value: Any) -> str:
    return str(value or "").strip()


def truthy(value: Any) -> bool:
    return safe(value).lower() in {"1", "true", "yes", "y"}


def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", safe(value)).casefold()
    return re.sub(r"[^\w]+", "", value, flags=re.UNICODE)


def title_hash(value: str) -> str:
    return hashlib.sha256(normalize_title(value).encode("utf-8")).hexdigest()


def parse_datetime(value: Any) -> str | None:
    text = safe(value)
    if not text:
        return None
    try:
        from dateutil.parser import parse as parse_date  # type: ignore

        parsed = parse_date(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except Exception:
        pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).isoformat()
    except ValueError:
        return None


def iter_jsonld(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        graph = value.get("@graph")
        if graph is not None:
            yield from iter_jsonld(graph)
    elif isinstance(value, list):
        for item in value:
            yield from iter_jsonld(item)


def read_jsonld(soup: BeautifulSoup) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for node in soup.select('script[type="application/ld+json"]'):
        try:
            value = json.loads(node.get_text(" ", strip=True))
        except (TypeError, json.JSONDecodeError):
            continue
        items.extend(iter_jsonld(value))
    return items


def meta_content(soup: BeautifulSoup, *names: str) -> str:
    for name in names:
        node = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if node and safe(node.get("content")):
            return safe(node.get("content"))
        node = soup.find(attrs={"itemprop": name})
        if node:
            return safe(node.get("content")) or safe(node.get("datetime")) or safe(node.get_text(" ", strip=True))
    return ""


def extract_published_at(soup: BeautifulSoup, jsonld: list[dict[str, Any]], fallback: str = "") -> tuple[str, str]:
    candidates: list[tuple[str, str]] = []
    for name in ("article:published_time", "datePublished", "datepublished", "publish-date", "pubdate"):
        value = meta_content(soup, name)
        if value:
            candidates.append((value, f"meta:{name}"))
    for item in jsonld:
        for key in ("datePublished", "dateCreated", "uploadDate"):
            if safe(item.get(key)):
                candidates.append((safe(item.get(key)), f"jsonld:{key}"))
    time_node = soup.find("time", attrs={"datetime": True})
    if time_node:
        candidates.append((safe(time_node.get("datetime")), "html:time"))
    if fallback:
        candidates.append((fallback, "discovery"))
    for value, source in candidates:
        parsed = parse_datetime(value)
        if parsed:
            return parsed, source
    return "", ""


def extract_section(
    soup: BeautifulSoup,
    jsonld: list[dict[str, Any]],
    url: str,
    feed_categories: Iterable[str] = (),
) -> tuple[str | None, str | None]:
    for category in feed_categories:
        value = safe(category)
        if value:
            return value, "rss_category"
    value = meta_content(soup, "article:section", "section")
    if value:
        return value, "meta"
    for item in jsonld:
        value = item.get("articleSection")
        if isinstance(value, list):
            value = next((safe(part) for part in value if safe(part)), "")
        if safe(value):
            return safe(value), "json_ld"
    parts = [part for part in urlsplit(url).path.split("/") if part]
    for part in parts[:-1]:
        value = re.sub(r"[-_]+", " ", part).strip()
        if value.casefold() not in GENERIC_SECTIONS and not value.isdigit() and len(value) >= 3:
            return value, "url_path"
    return None, None


def extract_title(soup: BeautifulSoup, jsonld: list[dict[str, Any]], fallback: str = "") -> str:
    # A page often contains Organization/WebSite JSON-LD before NewsArticle.
    # Search every object for a headline first so the publisher's generic
    # ``name`` does not replace the actual article title.
    for item in jsonld:
        if safe(item.get("headline")):
            return safe(item.get("headline"))
    for item in jsonld:
        item_type = item.get("@type")
        types = item_type if isinstance(item_type, list) else [item_type]
        if any("article" in safe(value).casefold() for value in types):
            if safe(item.get("name")):
                return safe(item.get("name"))
    for selector in ('meta[property="og:title"]', 'meta[name="twitter:title"]'):
        node = soup.select_one(selector)
        if node and safe(node.get("content")):
            return safe(node.get("content"))
    heading = soup.find("h1")
    if heading and safe(heading.get_text(" ", strip=True)):
        return safe(heading.get_text(" ", strip=True))
    if soup.title and safe(soup.title.get_text(" ", strip=True)):
        return safe(soup.title.get_text(" ", strip=True))
    return safe(fallback)


def strip_non_article_nodes(soup: BeautifulSoup) -> None:
    selectors = [
        "script", "style", "noscript", "nav", "footer", "header", "aside",
        "[class*='cookie']", "[id*='cookie']", "[class*='consent']", "[id*='consent']",
        "[class*='privacy']", "[aria-label*='cookie' i]",
    ]
    for selector in selectors:
        for node in soup.select(selector):
            node.decompose()


def extract_body(html: str, url: str, body_selector: str = "") -> str:
    body = safe(trafilatura.extract(
        html,
        url=url,
        include_comments=False,
        include_tables=False,
        favor_precision=True,
    ))
    soup = BeautifulSoup(html, "html.parser")
    strip_non_article_nodes(soup)
    selectors = [body_selector] if body_selector else []
    selectors.extend([
        '[itemprop="articleBody"]', "article", "main article", ".article-body",
        ".story-body", ".entry-content", ".article__body", ".formatted", "main",
    ])
    best = body
    for selector in selectors:
        if not selector:
            continue
        try:
            nodes = soup.select(selector)
        except Exception:
            continue
        for node in nodes:
            paragraphs = [safe(p.get_text(" ", strip=True)) for p in node.find_all("p")]
            text = "\n".join(part for part in paragraphs if part)
            if len(text) > len(best):
                best = text
    return safe(best)


def is_wall_content(title: str, body: str) -> tuple[bool, str]:
    normalized_title = unicodedata.normalize("NFKC", safe(title)).casefold()
    normalized_body = unicodedata.normalize("NFKC", safe(body)).casefold()
    for pattern in WALL_TITLE_PATTERNS:
        if pattern in normalized_title:
            return True, f"WALL_TITLE:{pattern}"
    for pattern in WALL_BODY_PATTERNS:
        if pattern in normalized_body:
            return True, f"WALL_BODY:{pattern}"
    return False, ""


def title_keywords(title: str) -> list[str]:
    text = unicodedata.normalize("NFKC", safe(title)).casefold()
    latin = [
        word for word in re.findall(r"[a-zà-žß]{4,}", text)
        if word not in LATIN_STOPWORDS
    ]
    cjk_runs = re.findall(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7a3]{2,}", text)
    cjk: list[str] = []
    for run in cjk_runs:
        if len(run) <= 8:
            cjk.append(run)
        else:
            cjk.extend(run[index:index + 3] for index in range(0, len(run) - 2, 2))
    return list(dict.fromkeys(latin + cjk))[:20]


def title_body_matches(title: str, body: str) -> bool:
    body_normalized = unicodedata.normalize("NFKC", safe(body)).casefold()
    keywords = title_keywords(title)
    if not keywords:
        return True
    hits = sum(keyword in body_normalized for keyword in keywords)
    return hits >= max(1, (len(keywords) + 3) // 4)


def has_long_line(body: str, minimum: int = 40) -> bool:
    return any(len(line.strip()) > minimum for line in safe(body).splitlines())


def source_quality_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    count = len(rows)
    titles = Counter(normalize_title(safe(row.get("title"))) for row in rows if safe(row.get("title")))
    top_title, top_count = titles.most_common(1)[0] if titles else ("", 0)
    real_dates = sum(bool(safe(row.get("published_at"))) and not truthy(row.get("published_at_estimated")) for row in rows)
    matches = sum(title_body_matches(safe(row.get("title")), safe(row.get("body"))) for row in rows)
    long_lines = sum(has_long_line(safe(row.get("body"))) for row in rows)
    wall_count = sum(is_wall_content(safe(row.get("title")), safe(row.get("body")))[0] for row in rows)
    return {
        "article_count": count,
        "top_title_hash": top_title,
        "top_title_count": top_count,
        "top_title_ratio": top_count / count if count else 0.0,
        "title_body_match_count": matches,
        "title_body_match_ratio": matches / count if count else 0.0,
        "long_line_count": long_lines,
        "long_line_ratio": long_lines / count if count else 0.0,
        "real_published_at_count": real_dates,
        "real_published_at_missing_ratio": 1 - (real_dates / count) if count else 0.0,
        "wall_content_count": wall_count,
        "short_body_under_500_count": sum(len(safe(row.get("body"))) < 500 for row in rows),
    }


def source_failure_reasons(summary: dict[str, Any], minimum_sample: int = 10) -> list[str]:
    count = int(summary["article_count"])
    reasons: list[str] = []
    if int(summary["wall_content_count"]) > 0:
        reasons.append("WALL_OR_ERROR_CONTENT")
    if count >= minimum_sample and float(summary["top_title_ratio"]) >= 0.30:
        reasons.append("TOP_TITLE_RATIO_GTE_30_PERCENT")
    if count >= minimum_sample and float(summary["title_body_match_ratio"]) < 0.60:
        reasons.append("TITLE_BODY_MATCH_RATIO_LT_60_PERCENT")
    if count and int(summary["long_line_count"]) == 0:
        reasons.append("NO_BODY_LINE_OVER_40_CHARS")
    if count >= minimum_sample and float(summary["real_published_at_missing_ratio"]) >= 1.0:
        reasons.append("PUBLISHED_AT_REAL_MISSING_100_PERCENT")
    return reasons
