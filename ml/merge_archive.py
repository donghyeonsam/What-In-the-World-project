#!/usr/bin/env python3
"""뉴스 raw 아카이브 병합 — 중복 제거 + 날짜 재분할.

  python merge_archive.py <입력파일...> --out-dir merged

하는 일
  1. 여러 아카이브 파일을 읽는다 (파일명은 신뢰하지 않는다)
  2. article_id 기준 중복 제거. 같은 id 면 필드가 더 많은 쪽(신포맷)을 남긴다
  3. 스키마 통일 — 구포맷에 없는 신규 필드는 null 로 채운다
  4. discovered_at 기준 정렬
  5. 전체 1개 파일 + discovered_at 실제 날짜별 파일로 출력
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

# 신포맷에만 있는 필드 — 구포맷 레코드는 null 로 채운다
NEW_FIELDS = ["section", "section_source",
              "published_at_estimated", "published_at_source"]


def field_score(r: dict) -> int:
    """정보량 점수. 같은 article_id 가 둘이면 높은 쪽을 남긴다."""
    return sum(1 for v in r.values() if v not in (None, "", []))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out-dir", default="merged")
    args = ap.parse_args()

    out = Path(args.out_dir)
    (out / "by_day").mkdir(parents=True, exist_ok=True)

    best: dict[str, dict] = {}
    stats = collections.Counter()
    per_file = collections.Counter()
    dup_pairs = collections.Counter()

    for path in args.inputs:
        name = Path(path).name
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                stats["lines"] += 1
                try:
                    r = json.loads(line)
                except Exception:
                    stats["parse_error"] += 1
                    continue

                aid = r.get("article_id")
                if not aid:
                    stats["no_article_id"] += 1
                    continue
                if not r.get("discovered_at"):
                    stats["no_discovered_at"] += 1
                    continue

                per_file[name] += 1
                prev = best.get(aid)
                if prev is None:
                    r["_src"] = name
                    best[aid] = r
                else:
                    stats["duplicate"] += 1
                    dup_pairs[tuple(sorted({prev["_src"], name}))] += 1
                    if field_score(r) > field_score(prev):
                        r["_src"] = name
                        best[aid] = r

    # 스키마 통일 + _src 제거
    rows = []
    for r in best.values():
        r.pop("_src", None)
        for k in NEW_FIELDS:
            r.setdefault(k, None)
        rows.append(r)

    rows.sort(key=lambda r: (r["discovered_at"], r["article_id"]))

    # 전체
    merged = out / "news.raw.merged.jsonl"
    with merged.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")

    # 날짜별
    by_day = collections.defaultdict(list)
    for r in rows:
        by_day[r["discovered_at"][:10]].append(r)
    for day, rs in sorted(by_day.items()):
        with (out / "by_day" / f"{day}.jsonl").open("w", encoding="utf-8") as f:
            for r in rs:
                f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")

    # ---- 리포트 -------------------------------------------------------
    print("=" * 62)
    print("입력")
    print("=" * 62)
    for n, c in per_file.most_common():
        print(f"  {n:<40}{c:>9,}")
    print(f"  {'합계':<40}{stats['lines']:>9,}")
    for k in ["parse_error", "no_article_id", "no_discovered_at"]:
        if stats[k]:
            print(f"  (제외 {k}: {stats[k]:,})")

    print()
    print("=" * 62)
    print("중복 제거")
    print("=" * 62)
    print(f"  중복 {stats['duplicate']:,}건 제거 → 고유 {len(rows):,}건")
    if dup_pairs:
        print("  중복이 걸친 파일 쌍:")
        for pair, c in dup_pairs.most_common(10):
            label = " ↔ ".join(pair) if len(pair) > 1 else f"{pair[0]} (파일 내)"
            print(f"    {label}  {c:,}건")

    print()
    print("=" * 62)
    print("날짜 재분할 (discovered_at 기준)")
    print("=" * 62)
    print(f"  {'날짜':<12}{'건수':>9}{'시작':>7}{'끝':>7}")
    for day, rs in sorted(by_day.items()):
        lo = rs[0]["discovered_at"][11:16]
        hi = rs[-1]["discovered_at"][11:16]
        print(f"  {day:<12}{len(rs):>9,}{lo:>7}{hi:>7}")

    print()
    filled = sum(1 for r in rows if r.get("section"))
    print(f"  신규 필드 보유(section): {filled:,}건 ({filled / len(rows):.0%})")
    print(f"  기간: {rows[0]['discovered_at'][:16]} ~ {rows[-1]['discovered_at'][:16]} UTC")
    print()
    print(f"출력  {merged}  ({merged.stat().st_size / 2**20:,.0f} MB)")
    print(f"      {out}/by_day/*.jsonl  ({len(by_day)}개)")


if __name__ == "__main__":
    main()
