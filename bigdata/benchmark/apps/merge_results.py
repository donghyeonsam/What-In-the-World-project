"""Validate worker shards and compare repeated single/distributed runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from collections import defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("results", type=Path, nargs="+")
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _global_result_checksum(results: list[dict]) -> str:
    lines = [
        f"{theme['theme_id']}:{theme['membership_checksum']}"
        for result in results
        for theme in result["theme_results"]
    ]
    digest = hashlib.sha256()
    for line in sorted(lines):
        digest.update(line.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _merge_run(results: list[dict]) -> dict:
    first = results[0]
    expected_nodes = set(first["expected_nodes"])
    actual_nodes = {result["node_id"] for result in results}
    if actual_nodes != expected_nodes or len(results) != len(expected_nodes):
        raise SystemExit(
            f"incomplete run: expected={sorted(expected_nodes)} "
            f"actual={sorted(actual_nodes)}"
        )
    if len({result["input_sha256"] for result in results}) != 1:
        raise SystemExit("workers used different input files")
    if len({result["assignment_sha256"] for result in results}) != 1:
        raise SystemExit("workers used different assignment files")
    if len({result["start_at_epoch"] for result in results}) != 1:
        raise SystemExit("workers did not use a common start time")

    all_themes = [theme for result in results for theme in result["assigned_themes"]]
    if len(all_themes) != len(set(all_themes)):
        raise SystemExit("a theme was processed by more than one node")

    return {
        "mode": first["mode"],
        "input_file": first["input_file"],
        "input_sha256": first["input_sha256"],
        "raw_rows": int(first["raw_rows"]),
        "node_count": len(expected_nodes),
        "wall_seconds": max(float(item["finished_at_epoch"]) for item in results)
        - float(first["start_at_epoch"]),
        "loaded_article_count": sum(int(item["loaded_article_count"]) for item in results),
        "result_checksum": _global_result_checksum(results),
        "parameters": first["parameters"],
    }


def main() -> None:
    args = parse_args()
    documents = [json.loads(path.read_text(encoding="utf-8")) for path in args.results]
    groups: dict[tuple[str, str, float], list[dict]] = defaultdict(list)
    for document in documents:
        key = (
            document["mode"],
            document["input_file"],
            float(document["start_at_epoch"]),
        )
        groups[key].append(document)
    runs = [_merge_run(group) for group in groups.values()]

    by_size_mode: dict[tuple[int, str], list[dict]] = defaultdict(list)
    for run in runs:
        by_size_mode[(run["raw_rows"], run["mode"])].append(run)

    lines = [
        "# 테마 정적 파티셔닝 Benchmark 결과",
        "",
        "| 입력 | 단일 시간 | 분산 시간 | 시간 단축 | Speedup | 분산 처리량 | 노드 |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for rows in sorted({run["raw_rows"] for run in runs}):
        single = by_size_mode.get((rows, "single"), [])
        distributed = by_size_mode.get((rows, "distributed"), [])
        if not single or not distributed:
            raise SystemExit(f"{rows:,} rows needs both single and distributed runs")
        all_runs = single + distributed
        if len({run["input_sha256"] for run in all_runs}) != 1:
            raise SystemExit(f"{rows:,} rows input checksum mismatch")
        if len({run["result_checksum"] for run in all_runs}) != 1:
            raise SystemExit(f"{rows:,} rows clustering result mismatch")
        if len({json.dumps(run["parameters"], sort_keys=True) for run in all_runs}) != 1:
            raise SystemExit(f"{rows:,} rows parameter mismatch")

        single_seconds = statistics.median(run["wall_seconds"] for run in single)
        distributed_seconds = statistics.median(run["wall_seconds"] for run in distributed)
        article_count = int(statistics.median(run["loaded_article_count"] for run in distributed))
        speedup = single_seconds / distributed_seconds
        reduction = (1.0 - distributed_seconds / single_seconds) * 100.0
        throughput = article_count / distributed_seconds
        node_count = max(run["node_count"] for run in distributed)
        lines.append(
            f"| {rows:,} | {single_seconds:.2f}s | {distributed_seconds:.2f}s | "
            f"{reduction:.1f}% | {speedup:.2f}x | {throughput:,.1f}건/s | {node_count} |"
        )

    lines.extend(
        [
            "",
            "> 시간은 공통 시작 시각부터 가장 늦게 끝난 노드까지이며, 전체 JSONL 스캔과 담당 테마 HDBSCAN을 포함합니다.",
            "",
        ]
    )
    rendered = "\n".join(lines)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
