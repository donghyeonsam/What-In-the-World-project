"""[stage 1.5, 선택] 집계 방식 선택 — 사람 라벨과 대조해 하나를 고른다.

주의 — 여기서 말하는 "사람 라벨" 은 검증용이지 학습용이 아니다.
  · student 가 배우는 라벨은 teacher 가 100% 만든다 (사람 0건)
  · 이 스크립트가 요구하는 150~400건은 학습에 들어가지 않는다.
    teacher 가 맞는지를 teacher 가 채점할 수 없어서 필요한 "자(尺)" 다.

건너뛰어도 파이프라인은 돈다. config 기본값(topk_mean)으로 진행된다.
다만 집계 방식이 맞는지, 특정 언어의 모델이 못 쓸 수준인지 알 수 없다.

라벨링(①)은 세 집계 방식의 값을 모두 저장한다. 이 스크립트가 그 값들을
사람 라벨과 대조해 어느 방식을 쓸지 정해 준다. 라벨링 재실행은 필요 없다.

두 가지를 함께 본다.
  1. 방식별 일치율 — 어느 집계가 사람 판단과 맞는가
  2. 축 비대칭    — 긍정·부정 가설의 기저율이 다른가 (weighted_mean 의 함정)

--- 사용법 -----------------------------------------------------------------

1) 검증 표본 뽑기 (분야 × 언어 층화)

    python -m distill.choose_aggregate sample --n 400

   → work/eval/to_label.csv  생성. article_id, lang, domain, title, body 앞부분.

2) 사람이 label 칼럼을 채운다 (positive / negative / neutral / mixed)
   가능하면 2~3명이 따로 채우고 다수결로 확정할 것.

3) 비교

    python -m distill.choose_aggregate compare --labels work/eval/labeled.csv

   → 방식별 일치율, 분야별·언어별 분해, 축 비대칭 리포트

4) 나온 결과로 config.yaml 의 aggregate.method 를 고치고 split 부터 재실행
"""
from __future__ import annotations

import argparse
import collections
import csv
import random
from pathlib import Path

import numpy as np

from .config import load_config, work_path
from .io_utils import read_all_shards
from .scoring import decide_label

METHODS = ("weighted_mean", "max", "topk_mean")


def _probs_for(row: dict, method: str, default_method: str) -> tuple[float, float] | None:
    """저장된 값에서 해당 방식의 (P긍정, P부정) 을 꺼낸다.

    config 로 고른 방식은 p_pos/p_neg 에, 나머지는 alt_agg 에 들어 있다.
    """
    if method == default_method:
        if row.get("p_pos") is None:
            return None
        return float(row["p_pos"]), float(row["p_neg"])
    alt = (row.get("alt_agg") or {}).get(method)
    return (float(alt[0]), float(alt[1])) if alt else None


# =====================================================================
# sample — 검증 표본 뽑기
# =====================================================================
def cmd_sample(cfg, args) -> None:
    rows = [r for r in read_all_shards(cfg.data.work_dir / "labels")
            if r.get("cat_pass") and r.get("tone_pass")]
    if not rows:
        raise SystemExit("라벨이 없다. 먼저 python -m distill.label 을 실행할 것")

    # 분야 × 언어 층화 — 한쪽에 몰린 표본으로 방식을 고르면 편향된 결정이 된다
    cells: dict[tuple, list] = collections.defaultdict(list)
    for r in rows:
        cells[(r["domain"], r["lang"])].append(r)

    rng = random.Random(cfg.split.seed)
    per_cell = max(1, args.n // max(len(cells), 1))
    picked: list[dict] = []
    for key in sorted(cells):
        group = cells[key]
        rng.shuffle(group)
        picked += group[:per_cell]
    rng.shuffle(picked)
    picked = picked[:args.n]

    out = work_path(cfg, "eval", "to_label.csv")
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["article_id", "lang", "domain", "label", "title", "body_head"])
        for r in picked:
            w.writerow([r["article_id"], r["lang"], r["domain"], "",
                        r["title"], (r.get("body") or "")[:600]])

    print(f"표본 {len(picked)}건 → {out}")
    print(f"  셀 {len(cells)}개, 셀당 최대 {per_cell}건")
    dist = collections.Counter((r["domain"], r["lang"]) for r in picked)
    print("\n  분야 × 언어 분포")
    langs = sorted({l for _, l in dist})
    print(f"    {'분야':<10}" + "".join(f"{l:>6}" for l in langs))
    for d in cfg.domains:
        print(f"    {d:<10}" + "".join(f"{dist[(d, l)]:>6}" for l in langs))
    print("\n  label 칼럼을 positive / negative / neutral / mixed 로 채운 뒤")
    print("  python -m distill.choose_aggregate compare --labels <파일> 실행")


# =====================================================================
# compare — 방식별 일치율 + 축 비대칭
# =====================================================================
def cmd_compare(cfg, args) -> None:
    valid = {"positive", "negative", "neutral", "mixed"}
    human: dict[str, str] = {}
    with Path(args.labels).open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            lab = (row.get("label") or "").strip().lower()
            if lab in valid:
                human[row["article_id"]] = lab
    if not human:
        raise SystemExit("label 칼럼에 유효한 값이 없다")
    print(f"사람 라벨 {len(human)}건")

    by_id = {r["article_id"]: r for r in read_all_shards(cfg.data.work_dir / "labels")}
    lab_cfg = cfg.labels
    default_method = cfg.aggregate.method

    # ---- 1. 방식별 일치율 ------------------------------------------
    print("\n" + "=" * 74)
    print("1. 집계 방식별 일치율")
    print("=" * 74)

    scores: dict[str, dict] = {}
    for m in METHODS:
        hit = miss = skipped = 0
        per_dom = collections.Counter(); per_dom_n = collections.Counter()
        per_lang = collections.Counter(); per_lang_n = collections.Counter()
        conf_mat = collections.Counter()
        for aid, truth in human.items():
            row = by_id.get(aid)
            if not row:
                skipped += 1; continue
            pp = _probs_for(row, m, default_method)
            if pp is None:
                skipped += 1; continue
            pred = decide_label(pp[0], pp[1], lab_cfg.mixed_threshold, lab_cfg.neutral_threshold)
            ok = pred == truth
            hit += ok; miss += (not ok)
            per_dom[row["domain"]] += ok; per_dom_n[row["domain"]] += 1
            per_lang[row["lang"]] += ok; per_lang_n[row["lang"]] += 1
            if not ok:
                conf_mat[(truth, pred)] += 1
        n = hit + miss
        scores[m] = {"acc": hit / n if n else 0.0, "n": n, "skipped": skipped,
                     "per_dom": (per_dom, per_dom_n), "per_lang": (per_lang, per_lang_n),
                     "conf": conf_mat}

    top_acc = max(s["acc"] for s in scores.values())
    for m in METHODS:
        s = scores[m]
        mark = "  ← 최고" if s["acc"] >= top_acc - 1e-9 else ""
        star = " (현재 config)" if m == default_method else ""
        print(f"  {m:<16} {s['acc']:.4f}  (n={s['n']}){star}{mark}")

    # 동점·근접(1%p 이내)이면 여러 개가 후보. 아래 축 비대칭으로 가린다.
    TIE = 0.01
    tied = [m for m in METHODS if scores[m]["acc"] >= top_acc - TIE]
    if len(tied) > 1:
        print(f"\n  {len(tied)}개 방식이 {TIE:.0%}p 이내로 근접: {', '.join(tied)}")
        print("  → 3절에서 축 비대칭을 함께 보고 가린다")

    print("\n  분야별")
    print(f"    {'분야':<10}" + "".join(f"{m[:9]:>12}" for m in METHODS))
    for d in cfg.domains:
        cells = ""
        for m in METHODS:
            h, t = scores[m]["per_dom"]
            cells += f"{(h[d]/t[d] if t[d] else 0):>11.3f}" + " "
        print(f"    {d:<10}{cells}")

    print("\n  언어별")
    langs = sorted({r["lang"] for r in by_id.values() if r["article_id"] in human})
    print(f"    {'언어':<10}" + "".join(f"{m[:9]:>12}" for m in METHODS))
    for l in langs:
        cells = ""
        for m in METHODS:
            h, t = scores[m]["per_lang"]
            cells += f"{(h[l]/t[l] if t[l] else 0):>11.3f}" + " "
        print(f"    {l:<10}{cells}")

    ref = tied[0]
    print(f"\n  {ref} 의 주요 오분류 (정답 → 예측)")
    if scores[ref]["conf"]:
        for (t, p), c in scores[ref]["conf"].most_common(6):
            print(f"    {t:<9} → {p:<9} {c}건")
    else:
        print("    오분류 없음")

    # ---- 2. 축 비대칭 ----------------------------------------------
    print("\n" + "=" * 74)
    print("2. 축 비대칭 — 중립 청크에서 긍정·부정 기저값이 같은가")
    print("=" * 74)
    print("  두 값이 크게 다르면 가설 기저율이 비대칭이라는 뜻이고,")
    print("  weighted_mean 이 그 편향을 중립 청크 수만큼 누적한다.\n")

    base: dict[str, list] = collections.defaultdict(list)
    for r in by_id.values():
        if r.get("neu_base"):
            base[r["domain"]].append(r["neu_base"])

    risky_domains: list[str] = []
    if not base:
        print("  neu_base 기록이 없다 — 라벨링을 최신 label.py 로 다시 돌려야 한다")
    else:
        print(f"  {'분야':<10}{'n':>6}{'긍정 기저':>11}{'부정 기저':>11}{'차이':>9}   판정")
        for d in cfg.domains:
            vals = base.get(d)
            if not vals:
                print(f"  {d:<10}{'—':>6}"); continue
            arr = np.array(vals)
            bp, bn = arr[:, 0].mean(), arr[:, 1].mean()
            diff = bn - bp
            if abs(diff) < 0.05:
                verdict = "양호"
            elif abs(diff) < 0.12:
                verdict = "주의 — 가설 문구 검토"
            else:
                verdict = "위험 — 평균 계열 부적합"
                risky_domains.append(d)
            print(f"  {d:<10}{len(vals):>6}{bp:>11.3f}{bn:>11.3f}{diff:>+9.3f}   {verdict}")
        print("\n  차이 > 0 = 부정 가설이 중립 텍스트에 더 잘 걸림 (부정으로 기울 위험)")

    # ---- 3. 권고 ----------------------------------------------------
    print("\n" + "=" * 74)
    print("3. 권고")
    print("=" * 74)

    # 축 비대칭이 심하면 중립 청크를 다 넣는 weighted_mean 은 편향을 누적한다.
    # 일치율이 근접한 후보가 있으면 그쪽을 택한다.
    choice = tied[0]
    if risky_domains and "weighted_mean" in tied:
        alt = [m for m in tied if m != "weighted_mean"]
        if alt:
            choice = alt[0]
            print(f"  일치율은 {', '.join(tied)} 가 근접하지만,")
            print(f"  {len(risky_domains)}개 분야({', '.join(risky_domains)})에서 축 비대칭이 크다.")
            print(f"  weighted_mean 은 중립 청크 수만큼 그 편향을 누적하므로 제외한다.\n")
        else:
            print("  [경고] weighted_mean 만 후보인데 축 비대칭이 크다.")
            print("  가설 문구를 대칭으로 고쳐 라벨링을 다시 돌리는 편이 낫다.\n")

    print(f"  → config.yaml 의 aggregate.method 를 '{choice}' 로 설정")
    if choice == "topk_mean":
        print(f"     topk 값도 바꿔가며 재실행해 볼 것 (현재 {cfg.aggregate.topk})")
    print("  → 그 다음 python -m distill.split 부터 재실행 (라벨링 재실행 불필요)")

    if risky_domains:
        print(f"\n  [별도 조치] 축 비대칭이 큰 분야의 가설 문구를 대칭으로 다듬을 것.")
        print("  hypotheses.py 에서 긍정·부정이 같은 문장 구조를 갖고,")
        print("  한쪽에만 중립 텍스트에 흔한 단어(risk, 우려, 과제 등)가 없는지 확인.")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("sample", help="검증 표본 CSV 생성")
    p1.add_argument("--n", type=int, default=400)

    p2 = sub.add_parser("compare", help="사람 라벨과 대조")
    p2.add_argument("--labels", required=True, help="label 칼럼을 채운 CSV")

    args = ap.parse_args()
    cfg = load_config()
    (cmd_sample if args.cmd == "sample" else cmd_compare)(cfg, args)


if __name__ == "__main__":
    main()
