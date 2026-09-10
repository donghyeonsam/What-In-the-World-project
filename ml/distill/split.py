"""[2] 게이트 통과분만 모아 train/val 분할.

python -m distill.split

입력: work/labeled.NNNNN.jsonl
출력: work/train.jsonl, work/val.jsonl, work/split_report.json

(분야 × 언어) 24칸으로 층화한다. 칸이 val에도 고루 들어가야
언어별 평가가 의미를 갖는다.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict

from .config import load_config, work_path
from .io_utils import read_shards, write_jsonl

KEEP_FIELDS = ("id", "url", "source", "country", "lang", "title", "body",
               "category", "category_probs", "cat_p1", "cat_margin",
               "sentiment", "alt_agg", "diag")


def slim(rec: dict) -> dict:
    """청크 배열은 학습에 필요 없다. 용량을 줄인다 (choose_aggregate는 샤드를 직접 읽음)."""
    return {k: rec[k] for k in KEEP_FIELDS if k in rec}


def run(cfg) -> dict:
    wd = work_path(cfg, ".keep").parent
    rows = [r for r in read_shards(wd, "labeled") if r.get("gate_pass")]
    if not rows:
        raise SystemExit("게이트를 통과한 기사가 없음. label_report.json의 gate_reasons 확인")

    rnd = random.Random(int(cfg.get("seed", 42)))
    keys = cfg.split.get("stratify_by", ["category", "lang"])
    buckets: dict = defaultdict(list)
    for r in rows:
        buckets[tuple(r.get(k) for k in keys)].append(r)

    ratio = float(cfg.split["val_ratio"])
    train: list[dict] = []
    val: list[dict] = []
    thin: list[str] = []
    for k in sorted(buckets):
        pool = buckets[k][:]
        rnd.shuffle(pool)
        n_val = max(1, round(len(pool) * ratio)) if len(pool) >= 10 else 0
        val.extend(pool[:n_val])
        train.extend(pool[n_val:])
        if len(pool) < int(cfg.student.get("min_train_per_category", 50)):
            thin.append(f"{'/'.join(map(str, k))}={len(pool)}")
    rnd.shuffle(train)
    rnd.shuffle(val)

    tp = work_path(cfg, "train.jsonl")
    vp = work_path(cfg, "val.jsonl")
    write_jsonl(tp, (slim(r) for r in train))
    write_jsonl(vp, (slim(r) for r in val))

    def dist(rs: list[dict], f: str) -> dict:
        return dict(Counter(r[f] for r in rs).most_common())

    report = {
        "gate_passed": len(rows),
        "train": len(train), "val": len(val),
        "by_category": dist(rows, "category"),
        "by_lang": dist(rows, "lang"),
        "by_label": dict(Counter(r["sentiment"]["label"] for r in rows).most_common()),
        "cells": {"|".join(map(str, k)): len(v) for k, v in sorted(buckets.items())},
        "thin_cells": thin,
    }
    work_path(cfg, "split_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[split] 통과 {len(rows):,} → train {len(train):,} / val {len(val):,}")
    print(f"  분야: {report['by_category']}")
    print(f"  언어: {report['by_lang']}")
    print(f"  라벨: {report['by_label']}")
    if thin:
        print(f"  ⚠ 물량 부족 칸: {', '.join(thin)}")
        print("    → 해당 분야 student는 학습이 건너뛰어질 수 있다 (수집 확대 필요)")
    print(f"  → {tp}, {vp}")
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="[2] train/val 분할")
    ap.add_argument("--config", default=None)
    a = ap.parse_args()
    run(load_config(a.config))


if __name__ == "__main__":
    main()
