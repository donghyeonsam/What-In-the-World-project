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


def tone_pass(row: dict, gates) -> bool:
    """teacher 판정을 학습에 쓸지 결정한다.

    왜 max(p_pos, p_neg) 로 거르면 안 되는가
      p_pos 는 "긍정 가설이 함의되는가" 의 확률이다. 0.15 는 확신이 없다는
      뜻이 아니라 "확실히 아니다" 라는 뜻이다. 확신의 척도는 값의 크기가
      아니라 0.5 에서 떨어진 거리다.

        명백한 중립   p=(0.15, 0.12)  teacher 는 확신함  → 넣어야 한다
        진짜 애매함   p=(0.52, 0.48)  teacher 는 모름    → 빼야 한다

      max 기준은 둘을 구분하지 못하고 같이 버린다. 그 결과 neutral 라벨이
      정의상 단 한 건도 학습에 들어가지 못한다 (neutral 은 둘 다 0.4 미만인데
      게이트는 max 0.6 이상을 요구하므로 교집합이 공집합이다).
      그러면 student 는 중립을 출력하는 법을 배우지 못한다.

    왜 'both'(min) 가 아니라 'any'(max) 인가
      both 로 걸면 한 축만 애매해도 기사를 통째로 버린다.

        (0.75, 0.55)  긍정은 명확, 부정만 미정  → both 탈락 / any 통과

      실측에서 both 를 쓰자 중간 지대 19,790건이 빠지면서 극단만 남았고,
      POLITICS negative 74.6%→81.3%, TECH positive 84.1%→86.6% 로 쏠림이
      오히려 커졌다. 그 상태로 학습하면 student 는 기사가 아니라 분야를
      외운다. any 는 옛 기준 통과분을 모두 포함한다
      (max(p)>=0.60 이면 그 축의 |p-0.5|>=0.10 이므로 수학적으로 보장된다).

      any 로 버려지는 것은 두 축이 모두 0.40~0.60 안에 있는 기사뿐이고,
      그것이 "teacher 가 정말 모르겠다" 의 정확한 정의다.

    mode
      margin    : |p-0.5| 기반 (기본)
                    margin_axes: any  → max(...)  ← 권장
                    margin_axes: both → min(...)
      max_prob  : max(p_pos, p_neg) >= tone_min_conf   (옛 기준. 중립 전량 탈락)
    """
    p_pos, p_neg = row.get("p_pos"), row.get("p_neg")
    if p_pos is None or p_neg is None:
        return False

    if getattr(gates, "mode", "margin") == "max_prob":
        return max(p_pos, p_neg) >= float(gates.tone_min_conf)

    d_pos, d_neg = abs(p_pos - 0.5), abs(p_neg - 0.5)
    margin = (min(d_pos, d_neg)
              if getattr(gates, "margin_axes", "any") == "both"
              else max(d_pos, d_neg))
    return margin >= float(getattr(gates, "tone_min_margin", 0.10))


def main() -> None:
    cfg = load_config()
    labels_dir = cfg.data.work_dir / "labels"
    rng = random.Random(cfg.split.seed)
    fields = ({int(k): v for k, v in cfg.fields.items()}
              if isinstance(cfg.fields, dict) else dict(enumerate(cfg.fields, 1)))
    field_names = [fields[k] for k in sorted(fields)]

    all_rows = list(read_all_shards(labels_dir))

    # ---- 톤 게이트 — 저장된 확률로 여기서 다시 계산한다 --------------------
    # label 단계의 tone_pass 플래그를 그대로 쓰지 않는 이유:
    # 기준을 바꿀 때마다 teacher 를 51분씩 다시 돌릴 이유가 없다.
    # p_pos / p_neg 는 이미 샤드에 있으므로 판정만 다시 하면 된다.
    passed = [r for r in all_rows if tone_pass(r, cfg.gates)]
    mode = getattr(cfg.gates, "mode", "margin")
    print(f"라벨 {len(all_rows):,}건 → 톤 게이트 통과 {len(passed):,}건 "
          f"({len(passed) / max(len(all_rows), 1) * 100:.1f}%)  [기준: {mode}]")

    # 옛 기준과의 차이를 보여준다 — 무엇이 새로 들어왔는지 눈으로 확인
    legacy = sum(1 for r in all_rows if r.get("tone_pass"))
    if mode != "max_prob":
        added = [r for r in passed if not r.get("tone_pass")]
        n_removed = legacy - (len(passed) - len(added))
        print(f"  옛 기준(max_prob {cfg.gates.tone_min_conf}) 통과 {legacy:,}건 대비  "
              f"+{len(added):,} / -{max(n_removed, 0):,}")
        if added:
            c = collections.Counter(r["tone_label"] for r in added)
            print("  새로 포함된 기사:",
                  ", ".join(f"{k} {v:,}" for k, v in c.most_common()))

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