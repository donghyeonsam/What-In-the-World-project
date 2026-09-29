"""Create deterministic, disjoint theme assignments for benchmark nodes."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from benchmark_common import parse_silver_line, sha256_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--mode", choices=("single", "distributed"), required=True)
    parser.add_argument("--nodes", nargs="+", required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    nodes = tuple(dict.fromkeys(args.nodes))
    if len(nodes) != len(args.nodes):
        raise SystemExit("node ids must be unique")
    if args.mode == "single" and len(nodes) != 1:
        raise SystemExit("single mode requires exactly one node")
    if not args.input.is_file():
        raise SystemExit(f"input does not exist: {args.input}")

    theme_counts: Counter[int] = Counter()
    raw_rows = 0
    valid_articles = 0
    seen_article_ids: set[str] = set()
    with args.input.open("rb") as source:
        for line in source:
            raw_rows += 1
            article = parse_silver_line(line)
            if article is None or article.article_id in seen_article_ids:
                continue
            seen_article_ids.add(article.article_id)
            valid_articles += 1
            theme_counts[article.theme_id] += 1

    assignments = {node: [] for node in nodes}
    estimated_loads = {node: 0 for node in nodes}
    for theme_id, count in sorted(
        theme_counts.items(), key=lambda item: (-item[1], item[0])
    ):
        node = min(nodes, key=lambda item: (estimated_loads[item], item))
        assignments[node].append(theme_id)
        estimated_loads[node] += count * count

    document = {
        "format_version": 1,
        "mode": args.mode,
        "input_file": args.input.name,
        "input_sha256": sha256_file(args.input),
        "raw_rows": raw_rows,
        "valid_articles": valid_articles,
        "nodes": list(nodes),
        "assignments": {
            node: sorted(theme_ids) for node, theme_ids in assignments.items()
        },
        "theme_article_counts": {
            str(theme_id): count for theme_id, count in sorted(theme_counts.items())
        },
        "estimated_node_loads": estimated_loads,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(args.output)
    for node in nodes:
        article_count = sum(theme_counts[value] for value in assignments[node])
        print(
            f"{node}: themes={len(assignments[node])} "
            f"articles={article_count:,} weight={estimated_loads[node]:,}"
        )


if __name__ == "__main__":
    main()
