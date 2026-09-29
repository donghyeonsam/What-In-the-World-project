"""Run one statically assigned clustering shard without a central master."""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing
import socket
import time
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import numpy as np

from benchmark_common import parse_silver_line, sha256_file
from issue_clustering import UnclassifiedArticle, cluster_articles


_THEME_ARTICLES: dict[int, list[UnclassifiedArticle]] = {}
_CLUSTER_CONFIG: dict[str, int | float] = {}


@dataclass(frozen=True)
class ThemeResult:
    theme_id: int
    article_count: int
    cluster_count: int
    clustered_article_count: int
    elapsed_seconds: float
    membership_checksum: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--node-id", required=True)
    parser.add_argument("--mode", choices=("single", "distributed"), required=True)
    parser.add_argument("--expected-rows", type=int, required=True)
    parser.add_argument("--assignment", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start-at", required=True, help="UTC ISO-8601 timestamp")
    parser.add_argument("--processes", type=int, required=True)
    parser.add_argument("--max-articles-per-theme", type=int, default=0)
    parser.add_argument("--min-cluster-size", type=int, default=8)
    parser.add_argument("--min-samples", type=int, default=4)
    parser.add_argument("--min-membership-confidence", type=float, default=0.8)
    parser.add_argument("--min-centroid-similarity", type=float, default=0.92)
    return parser.parse_args()


def _parse_start_at(value: str) -> float:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SystemExit("start-at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise SystemExit("start-at must include a timezone")
    return parsed.timestamp()


def _run_theme(theme_id: int) -> ThemeResult:
    articles = tuple(
        sorted(
            _THEME_ARTICLES[theme_id],
            key=lambda article: (article.unclassified_at, article.article_id),
        )
    )
    max_articles = int(_CLUSTER_CONFIG["max_articles_per_theme"])
    if max_articles > 0:
        articles = articles[:max_articles]

    started = time.perf_counter()
    clusters = cluster_articles(
        articles,
        min_cluster_size=int(_CLUSTER_CONFIG["min_cluster_size"]),
        min_samples=int(_CLUSTER_CONFIG["min_samples"]),
        min_membership_confidence=float(
            _CLUSTER_CONFIG["min_membership_confidence"]
        ),
        min_centroid_similarity=float(_CLUSTER_CONFIG["min_centroid_similarity"]),
    )
    elapsed = time.perf_counter() - started
    memberships = [
        ",".join(sorted(article.article_id for article in cluster.articles))
        for cluster in clusters
    ]
    checksum = hashlib.sha256("\n".join(memberships).encode("utf-8")).hexdigest()
    return ThemeResult(
        theme_id=theme_id,
        article_count=len(articles),
        cluster_count=len(clusters),
        clustered_article_count=sum(len(cluster.articles) for cluster in clusters),
        elapsed_seconds=elapsed,
        membership_checksum=checksum,
    )


def main() -> None:
    global _THEME_ARTICLES, _CLUSTER_CONFIG
    args = parse_args()
    if args.processes < 1:
        raise SystemExit("processes must be positive")
    assignment = json.loads(args.assignment.read_text(encoding="utf-8"))
    if args.mode != assignment["mode"]:
        raise SystemExit(
            f"mode does not match assignment: expected {assignment['mode']}"
        )
    if args.expected_rows != int(assignment["raw_rows"]):
        raise SystemExit(
            "expected-rows does not match assignment: "
            f"expected {assignment['raw_rows']}"
        )
    if args.node_id not in assignment["assignments"]:
        raise SystemExit(f"node id is not present in assignment: {args.node_id}")
    if args.input.name != assignment["input_file"]:
        raise SystemExit("input filename does not match assignment")
    actual_sha256 = sha256_file(args.input)
    if actual_sha256 != assignment["input_sha256"]:
        raise SystemExit("input SHA-256 does not match assignment")

    assigned_themes = set(int(value) for value in assignment["assignments"][args.node_id])
    start_at_epoch = _parse_start_at(args.start_at)
    wait_seconds = start_at_epoch - time.time()
    if wait_seconds < -5.0:
        raise SystemExit(
            f"start-at is already {-wait_seconds:.1f}s in the past; choose a new time"
        )
    if wait_seconds > 0:
        print(
            f"READY node={args.node_id} themes={len(assigned_themes)} "
            f"start_at={args.start_at}",
            flush=True,
        )
        time.sleep(wait_seconds)

    actual_started_epoch = time.time()
    pipeline_started = time.perf_counter()
    articles_by_theme: dict[int, list[UnclassifiedArticle]] = defaultdict(list)
    seen_article_ids: set[str] = set()
    raw_rows = 0
    rejected_rows = 0
    with args.input.open("rb") as source:
        for line in source:
            raw_rows += 1
            parsed = parse_silver_line(line)
            if parsed is None:
                rejected_rows += 1
                continue
            if parsed.theme_id not in assigned_themes:
                continue
            if parsed.article_id in seen_article_ids:
                rejected_rows += 1
                continue
            seen_article_ids.add(parsed.article_id)
            article = UnclassifiedArticle(
                article_id=parsed.article_id,
                theme_id=parsed.theme_id,
                embedding=np.asarray(parsed.embedding, dtype=np.float64),
                title=parsed.title,
                summary=parsed.summary,
                published_at=parsed.published_at,
                unclassified_at=parsed.published_at,
            )
            articles_by_theme[article.theme_id].append(article)
    load_seconds = time.perf_counter() - pipeline_started

    missing_themes = assigned_themes - set(articles_by_theme)
    if missing_themes:
        raise RuntimeError(f"assigned themes have no valid articles: {sorted(missing_themes)}")

    _THEME_ARTICLES = dict(articles_by_theme)
    _CLUSTER_CONFIG = {
        "max_articles_per_theme": args.max_articles_per_theme,
        "min_cluster_size": args.min_cluster_size,
        "min_samples": args.min_samples,
        "min_membership_confidence": args.min_membership_confidence,
        "min_centroid_similarity": args.min_centroid_similarity,
    }
    clustering_started = time.perf_counter()
    process_count = min(args.processes, max(1, len(assigned_themes)))
    with multiprocessing.get_context("fork").Pool(processes=process_count) as pool:
        theme_results = pool.map(_run_theme, sorted(assigned_themes))
    clustering_seconds = time.perf_counter() - clustering_started
    pipeline_seconds = time.perf_counter() - pipeline_started
    finished_at_epoch = time.time()

    summary = {
        "format_version": 1,
        "mode": args.mode,
        "node_id": args.node_id,
        "hostname": socket.gethostname(),
        "input_file": args.input.name,
        "input_sha256": actual_sha256,
        "raw_rows": raw_rows,
        "assignment_file": args.assignment.name,
        "assignment_sha256": sha256_file(args.assignment),
        "expected_nodes": assignment["nodes"],
        "assigned_themes": sorted(assigned_themes),
        "loaded_article_count": sum(len(values) for values in articles_by_theme.values()),
        "rejected_or_duplicate_rows": rejected_rows,
        "processes": process_count,
        "start_at": args.start_at,
        "start_at_epoch": start_at_epoch,
        "actual_started_epoch": actual_started_epoch,
        "started_late_seconds": max(0.0, actual_started_epoch - start_at_epoch),
        "finished_at_epoch": finished_at_epoch,
        "load_seconds": load_seconds,
        "clustering_seconds": clustering_seconds,
        "pipeline_seconds": pipeline_seconds,
        "parameters": _CLUSTER_CONFIG,
        "theme_results": [asdict(result) for result in theme_results],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"DONE node={args.node_id} articles={summary['loaded_article_count']} "
        f"seconds={pipeline_seconds:.3f} output={args.output}",
        flush=True,
    )


if __name__ == "__main__":
    main()
