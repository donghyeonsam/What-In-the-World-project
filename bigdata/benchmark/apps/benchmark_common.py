"""Shared parsing and checksum functions for the standalone benchmark."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ParsedArticle:
    article_id: str
    theme_id: int
    embedding: list[float]
    title: str
    summary: str | None
    published_at: str


def parse_silver_payload(payload: object) -> ParsedArticle | None:
    if not isinstance(payload, dict):
        return None
    try:
        nlp = payload["nlp_worker_data"]
        theme_id = nlp["theme_id"]
        article_id = payload["article_id"]
        published_at = payload["published_at"]
        embedding = nlp.get("summary_embedding") or nlp["article_embedding"]
        title = payload.get("title") or article_id
        summary = nlp.get("summary")
    except (KeyError, TypeError):
        return None

    if (
        isinstance(theme_id, bool)
        or not isinstance(theme_id, int)
        or theme_id <= 0
        or not isinstance(article_id, str)
        or not article_id.strip()
        or not isinstance(published_at, str)
        or not published_at.strip()
        or not isinstance(embedding, list)
        or not embedding
    ):
        return None
    try:
        numeric_embedding = [float(value) for value in embedding]
    except (TypeError, ValueError):
        return None
    if any(not math.isfinite(value) for value in numeric_embedding):
        return None

    return ParsedArticle(
        article_id=article_id.strip(),
        theme_id=theme_id,
        embedding=numeric_embedding,
        title=str(title),
        summary=str(summary) if summary is not None else None,
        published_at=published_at,
    )


def parse_silver_line(line: bytes) -> ParsedArticle | None:
    try:
        payload = json.loads(line)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return parse_silver_payload(payload)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()
