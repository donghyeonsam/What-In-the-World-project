"""[stage 2] 분할 — work/labels/*.jsonl → work/splits/{FIELD}/{train,val}.jsonl

하는 일
  1. 톤 게이트 통과분만 남긴다 (분야는 worker 분류기가 이미 정했다)
  2. 분야별로 나눈다 — 톤 student 가 분야마다 하나씩이므로
  3. 각 분야 안에서 언어별로 층화해 train/val 을 나눈다
     (언어 비율이 train 과 val 에서 같아야 언어별 검증이 의미 있다)
  4. 분야 × 언어 교차표를 출력한다 — 어느 조합이 부족한지 여기서 보인다

실행
    python -m distill.split
"""
from __future__ import annotations

import collections
import random

from .config import load_config, work_path
from .io_utils import read_all_shards, write_jsonl

# 학습에 필요한 필드만 남긴다 — 무거운 원본 메타는 여기서 정리
KEEP = ["article_id", "lang", "country", "source_name", "title", "body",
        "field", "field_id", "theme_code", "theme_similarity",
        "p_pos", "p_neg", "tone_label", "tone_point", "tone_conf"]


def main() -> None:
    cfg = load_config()
    labels_dir = cfg.data.work_dir / "labels"
    rng = random.Random(cfg.split.seed)
    fields = ({int(k): v for k, v in cfg.fields.items()}
              if isinstance(cfg.fields, dict) else dict(enumerate(cfg.fields, 1)))
    field_names = [fields[k] for k in sorted(fields)]

    all_rows = list(read_all_shards(labels_dir))
    passed = [r for r in all_rows if r.get("tone_pass")]
    print(f"라벨 {len(all_rows):,}건 → 톤 게이트 통과 {len(passed):,}건 "
          f"({len(passed) / max(len(all_rows), 1) * 100:.1f}%)")

    by_field: dict[str, list[dict]] = collections.defaultdict(list)
    for r in passed:
        by_field[r["field"]].append({k: r.get(k) for k in KEEP})

    # ---- 교차표 ---------------------------------------------------------
    langs = sorted({r["lang"] for r in passed})
    print("\n=== 분야 × 언어 (톤 게이트 통과분) ===")
    print(f"  {'분야':<10}" + "".join(f"{l:>8}" for l in langs) + f"{'합계':>9}")
    warn = []
    for f in field_names:
        row = collections.Counter(r["lang"] for r in by_field.get(f, []))
        print(f"  {f:<10}" + "".join(f"{row[l]:>8,}" for l in langs)
              + f"{sum(row.values()):>9,}")
        for l in langs:
            if row[l] < cfg.split.min_per_cell:
                warn.append((f, l, row[l]))
    total = collections.Counter(r["lang"] for r in passed)
    print(f"  {'합계':<10}" + "".join(f"{total[l]:>8,}" for l in langs)
          + f"{len(passed):>9,}")

    if warn:
        print(f"\n[경고] 조합당 {cfg.split.min_per_cell}건 미만:")
        for f, l, n in warn:
            print(f"  {f} × {l}: {n}건 — 이 조합은 검증 결과를 신뢰하기 어렵습니다")

    # 학습 충분성 — 400건 목표
    thin = []
    for f in field_names:
        row = collections.Counter(r["lang"] for r in by_field.get(f, []))
        for l in langs:
            if row[l] < 400:
                thin.append((f, l, row[l]))
    if thin:
        print("\n[참고] 400건 미만인 칸 (그 언어 성능이 낮게 나올 수 있음):")
        for f, l, n in sorted(thin, key=lambda x: x[2]):
            print(f"  {f} × {l}: {n}건")

    # ---- 언어 층화 분할 -------------------------------------------------
    print("\n=== 분할 ===")
    for f in field_names:
        rows = by_field.get(f, [])
        if not rows:
            print(f"  {f}: 데이터 없음 — 건너뜀")
            continue

        train, val = [], []
        by_lang = collections.defaultdict(list)
        for r in rows:
            by_lang[r["lang"]].append(r)
        for l, group in by_lang.items():
            rng.shuffle(group)
            n_val = max(1, int(len(group) * cfg.split.val_ratio)) if len(group) >= 5 else 0
            val += group[:n_val]
            train += group[n_val:]
        rng.shuffle(train)

        write_jsonl(work_path(cfg, "splits", f, "train.jsonl"), train)
        write_jsonl(work_path(cfg, "splits", f, "val.jsonl"), val)
        print(f"  {f:<10} train {len(train):>7,} / val {len(val):>6,}")

    # ---- 라벨 분포 확인 --------------------------------------------------
    print("\n=== teacher 라벨 분포 (분야별) ===")
    print(f"  {'분야':<10}{'positive':>10}{'negative':>10}{'neutral':>10}{'mixed':>8}")
    for f in field_names:
        c = collections.Counter(r["tone_label"] for r in by_field.get(f, []))
        n = max(sum(c.values()), 1)
        print(f"  {f:<10}" + "".join(f"{c[k] / n:>9.1%} " for k in
                                     ["positive", "negative", "neutral", "mixed"]))
    print("\n  한쪽으로 90% 이상 몰린 분야가 있으면 가설 문구를 재검토하세요.")


if __name__ == "__main__":
    main()
