"""집계 방식 선택 도구. 선택 사항 — 확정은 topk_mean, topk=2.

python -m distill.choose_aggregate sample  --n 300 --out work/verify.jsonl
python -m distill.choose_aggregate compare --labels work/verify_filled.jsonl

sample  : 사람이 라벨을 채울 검증 시트를 뽑는다 (분야×언어 층화, 애매한 건 우선).
compare : 사람 라벨과 3방식을 대조해 정확도·MAE를 낸다.

teacher 추론 뒤의 넘파이 산수라 비용 0. 라벨링을 다시 돌릴 필요가 없다.
"""
from __future__ import annotations

import argparse
import json
import random
from collections import Counter, defaultdict

import numpy as np

from .config import load_config, work_path
from .io_utils import read_shards, write_jsonl
from .scoring import AGG_METHODS, aggregate, decide_label, tone_point

HUMAN_LABELS = ("positive", "negative", "neutral", "mixed")


def _has_chunks(rec: dict) -> bool:
    return bool(rec.get("chunks")) and rec["chunks"].get("n", 0) > 0


def cmd_sample(cfg, n: int, out: str, seed: int, ambiguous_ratio: float) -> None:
    rows = [r for r in read_shards(work_path(cfg, ".keep").parent, "labeled")
            if _has_chunks(r)]
    if not rows:
        raise SystemExit("라벨 샤드가 없음. 먼저 python -m distill.label 실행")

    rnd = random.Random(seed)
    # 방식 간 판정이 갈리는 기사를 우선 뽑는다. 여기서 방식 차이가 드러난다.
    def disputed(r: dict) -> int:
        labs = {decide_label(r["alt_agg"][m]["p_pos"], r["alt_agg"][m]["p_neg"],
                             float(cfg.labels["mixed_threshold"]),
                             float(cfg.labels["neutral_threshold"]))
                for m in AGG_METHODS}
        return len(labs)

    buckets: dict = defaultdict(list)
    for r in rows:
        buckets[(r["category"], r["lang"])].append(r)

    n_amb = int(n * ambiguous_ratio)
    picked: list[dict] = []
    keys = sorted(buckets)
    # 1) 층화 균등 추출
    per = max(1, (n - n_amb) // max(1, len(keys)))
    for k in keys:
        pool = buckets[k][:]
        rnd.shuffle(pool)
        picked.extend(pool[:per])
    # 2) 판정이 갈리는 것 채우기
    amb = sorted((r for r in rows if disputed(r) > 1),
                 key=lambda r: -disputed(r))
    rnd.shuffle(amb)
    have = {r["id"] for r in picked}
    for r in amb:
        if len(picked) >= n:
            break
        if r["id"] not in have:
            picked.append(r)
            have.add(r["id"])
    picked = picked[:n]

    sheet = [{
        "id": r["id"], "url": r["url"], "lang": r["lang"],
        "category": r["category"], "title": r["title"],
        "body_head": r["body"][:1500],
        "human_label": "",                    # positive/negative/neutral/mixed 중 하나를 채운다
        "human_note": "",
        "_teacher_label": r["sentiment"]["label"],   # 참고용. 보지 않고 채우는 게 좋다
    } for r in picked]

    write_jsonl(out, sheet)
    dist = Counter((r["category"], r["lang"]) for r in picked)
    print(f"[sample] {len(sheet)}건 → {out}")
    print(f"  칸 수 {len(dist)} / 칸당 최소 {min(dist.values())} 최대 {max(dist.values())}")
    print("  human_label 열을 채운 뒤 compare 서브커맨드를 실행")


def cmd_compare(cfg, labels_path: str) -> None:
    human = {}
    with open(labels_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            lab = (r.get("human_label") or "").strip().lower()
            if lab in HUMAN_LABELS:
                human[r["id"]] = lab
    if not human:
        raise SystemExit("human_label이 채워진 행이 없음")

    recs = {r["id"]: r for r in read_shards(work_path(cfg, ".keep").parent, "labeled")
            if _has_chunks(r)}
    common = [i for i in human if i in recs]
    print(f"[compare] 사람 라벨 {len(human)}건 / 대조 가능 {len(common)}건\n")

    mt = float(cfg.labels["mixed_threshold"])
    nt = float(cfg.labels["neutral_threshold"])
    topk = int(cfg.aggregate["topk"])
    truth_point = {"positive": 75.0, "negative": 25.0,
                   "neutral": 50.0, "mixed": 50.0}

    results = {}
    for m in AGG_METHODS:
        ok = 0
        errs: list[float] = []
        conf: Counter = Counter()
        for i in common:
            r = recs[i]
            pp, pn = aggregate(r["chunks"]["p_pos"], r["chunks"]["p_neg"],
                               r["chunks"]["tokens"], method=m, topk=topk)
            pred = decide_label(pp, pn, mt, nt)
            ok += int(pred == human[i])
            errs.append(abs(tone_point(pp, pn) - truth_point[human[i]]))
            conf[(human[i], pred)] += 1
        results[m] = {
            "accuracy": round(ok / len(common), 4),
            "point_mae": round(float(np.mean(errs)), 3),
            "confusion": {f"{a}→{b}": v for (a, b), v in conf.most_common()},
        }
        star = " ←" if m == cfg.aggregate["method"] else ""
        print(f"  {m:14s} acc={results[m]['accuracy']:.3f} "
              f"MAE={results[m]['point_mae']:.2f}{star}")

    best = max(results, key=lambda m: results[m]["accuracy"])
    print(f"\n  최고: {best} (현재 설정: {cfg.aggregate['method']})")
    if best != cfg.aggregate["method"]:
        print(f"  → 바꾸려면 config.yaml의 aggregate.method를 {best}로 수정. "
              "라벨링 재실행은 필요 없다.")
    for m, v in results.items():
        print(f"\n  [{m}] 혼동")
        for k, c in list(v["confusion"].items())[:8]:
            print(f"    {k:26s} {c:>5}")

    out = work_path(cfg, "aggregate_compare.json")
    out.write_text(json.dumps({"n": len(common), "results": results},
                              ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  → {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description="집계 방식 선택 도구")
    ap.add_argument("--config", default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sample", help="사람 검증용 시트 추출")
    s.add_argument("--n", type=int, default=300)
    s.add_argument("--out", default="work/verify.jsonl")
    s.add_argument("--seed", type=int, default=42)
    s.add_argument("--ambiguous-ratio", type=float, default=0.4)

    c = sub.add_parser("compare", help="사람 라벨과 3방식 대조")
    c.add_argument("--labels", required=True)

    a = ap.parse_args()
    cfg = load_config(a.config)
    if a.cmd == "sample":
        cmd_sample(cfg, a.n, a.out, a.seed, a.ambiguous_ratio)
    else:
        cmd_compare(cfg, a.labels)


if __name__ == "__main__":
    main()
