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
CHECKPOINT_ARTICLES = 50_000


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


def _cluster_snapshot(
    articles_by_theme: dict[int, list[UnclassifiedArticle]],
    max_processes: int,
) -> list[ThemeResult]:
    global _THEME_ARTICLES

    active_themes = sorted(articles_by_theme)
    if not active_themes:
        return []

    # Forked workers see only the articles present when their pool was created.
    _THEME_ARTICLES = dict(articles_by_theme)
    with multiprocessing.get_context("fork").Pool(
        processes=min(max_processes, len(active_themes))
    ) as pool:
        return pool.map(_run_theme, active_themes)


def main() -> None:
    global _CLUSTER_CONFIG
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

    _CLUSTER_CONFIG = {
        "max_articles_per_theme": args.max_articles_per_theme,
        "min_cluster_size": args.min_cluster_size,
        "min_samples": args.min_samples,
        "min_membership_confidence": args.min_membership_confidence,
        "min_centroid_similarity": args.min_centroid_similarity,
    }
    process_count = min(args.processes, max(1, len(assigned_themes)))
    actual_started_epoch = time.time()
    pipeline_started = time.perf_counter()
    read_started = pipeline_started
    previous_checkpoint_finished = pipeline_started
    previous_checkpoint_articles = 0
    articles_by_theme: dict[int, list[UnclassifiedArticle]] = defaultdict(list)
    seen_article_ids: set[str] = set()
    raw_rows = 0
    accepted_articles = 0
    rejected_rows = 0
    load_seconds = 0.0
    clustering_seconds = 0.0
    checkpoint_count = 0
    theme_results: list[ThemeResult] = []
    milestone_log_path = args.output.with_suffix(".milestones.jsonl")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    with milestone_log_path.open("w", encoding="utf-8") as milestone_log:

        def record_checkpoint() -> None:
            nonlocal read_started, previous_checkpoint_finished
            nonlocal previous_checkpoint_articles, load_seconds
            nonlocal clustering_seconds, checkpoint_count, theme_results

            read_finished = time.perf_counter()
            chunk_load_seconds = read_finished - read_started
            clustering_started = time.perf_counter()
            theme_results = _cluster_snapshot(articles_by_theme, process_count)
            chunk_clustering_seconds = time.perf_counter() - clustering_started
            checkpoint_finished = time.perf_counter()
            checkpoint = {
                "format_version": 1,
                "mode": args.mode,
                "node_id": args.node_id,
                "input_file": args.input.name,
                "input_sha256": actual_sha256,
                "checkpoint_articles": accepted_articles,
                "chunk_articles": accepted_articles - previous_checkpoint_articles,
                "raw_rows_read": raw_rows,
                "loaded_article_count": sum(
                    len(values) for values in articles_by_theme.values()
                ),
                "rejected_or_duplicate_rows": rejected_rows,
                "load_seconds": chunk_load_seconds,
                "clustering_seconds": chunk_clustering_seconds,
                "interval_seconds": checkpoint_finished - previous_checkpoint_finished,
                "cumulative_seconds": checkpoint_finished - pipeline_started,
                "finished_at_epoch": time.time(),
                "theme_results": [asdict(result) for result in theme_results],
            }
            milestone_log.write(json.dumps(checkpoint, ensure_ascii=False) + "\n")
            milestone_log.flush()
            load_seconds += chunk_load_seconds
            clustering_seconds += chunk_clustering_seconds
            checkpoint_count += 1
            previous_checkpoint_articles = accepted_articles
            previous_checkpoint_finished = checkpoint_finished
            print(
                f"CHECKPOINT node={args.node_id} articles={accepted_articles} "
                f"interval={checkpoint['interval_seconds']:.3f}s "
                f"cumulative={checkpoint['cumulative_seconds']:.3f}s",
                flush=True,
            )
            read_started = time.perf_counter()

        with args.input.open("rb") as source:
            for line in source:
                raw_rows += 1
                parsed = parse_silver_line(line)
                if parsed is None:
                    rejected_rows += 1
                    continue
                if parsed.article_id in seen_article_ids:
                    rejected_rows += 1
                    continue
                seen_article_ids.add(parsed.article_id)
                accepted_articles += 1
                if parsed.theme_id in assigned_themes:
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
                if accepted_articles % CHECKPOINT_ARTICLES == 0:
                    record_checkpoint()

        if accepted_articles > previous_checkpoint_articles:
            record_checkpoint()

    if raw_rows != args.expected_rows:
        raise RuntimeError(
            f"input has {raw_rows} rows; assignment expects {args.expected_rows}"
        )
    missing_themes = assigned_themes - set(articles_by_theme)
    if missing_themes:
        raise RuntimeError(f"assigned themes have no valid articles: {sorted(missing_themes)}")

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
        "accepted_article_count": accepted_articles,
        "loaded_article_count": sum(len(values) for values in articles_by_theme.values()),
        "rejected_or_duplicate_rows": rejected_rows,
        "processes": process_count,
        "checkpoint_articles": CHECKPOINT_ARTICLES,
        "checkpoint_count": checkpoint_count,
        "milestone_log": milestone_log_path.name,
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
