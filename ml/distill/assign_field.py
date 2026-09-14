"""[stage 0.5] 분야 배정 — work/clean.jsonl → work/clean.field.jsonl

NLP worker 의 ThemeClassifier 를 오프라인에서 그대로 재현한다.

  기사 → E5 임베딩 → 68개 테마 임베딩과 코사인 → 최근접 테마 → field_id

왜 teacher 가 아니라 worker 분류기를 쓰나
  런타임에서 기사를 어느 톤 모델로 보낼지는 worker 가 정한다. 학습 데이터를
  teacher 기준으로 나누면 두 기준이 달라져, 런타임에 "자기 같은 기사를 본 적
  없는 모델" 에게 채점받는 기사가 생긴다. 같은 분류기를 양쪽에 쓰면 그 불일치가
  정의상 사라진다.

worker 와 반드시 같아야 하는 것 (하나라도 어긋나면 조용히 정확도만 떨어진다)
  · 임베딩 함수   worker 의 pipeline/embedding.py 를 직접 import 한다.
                  베끼지 않는다 — 베끼면 worker 가 바뀔 때 조용히 어긋난다.
  · centroid      worker 의 resources/centroid.npy 와 같은 파일
  · 카탈로그      worker 의 resources/theme_catalog.json 과 같은 파일

  → config.yaml 의 assign.worker_path 하나로 셋 다 따라간다.

실행
    python -m distill.assign_field
    python -m distill.assign_field --limit 2000      # 소규모 확인
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

import numpy as np

from .config import load_config, work_path
from .io_utils import read_jsonl, write_jsonl

EMBED_DIM = 768


# =====================================================================
# 카탈로그
# =====================================================================
def load_catalog(path: Path, centroid: np.ndarray | None = None
                 ) -> tuple[np.ndarray, list[dict]]:
    """theme_catalog.json → (정규화된 68×768 행렬, 메타 리스트).

    centroid 가 주어지면 정규화 '전에' 빼서 기사 임베딩과 같은 공간에 둔다.
    기사만 중심화하고 카탈로그를 그대로 두면 지금보다 나빠진다.
    """
    path = Path(path).expanduser()
    if not path.exists():
        raise FileNotFoundError(
            f"theme_catalog.json 을 찾을 수 없습니다: {path}\n"
            f"config.yaml 의 assign.catalog 를 확인하세요."
        )
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(catalog, list):
        raise ValueError("theme_catalog.json 의 최상위는 리스트여야 합니다.")

    raw, metas = [], []
    for item in catalog:
        v = np.asarray(item["embedding"], dtype=np.float32)
        if v.shape != (EMBED_DIM,):
            raise ValueError(f"theme_id={item['theme_id']} 차원 {v.shape}")
        if np.linalg.norm(v) == 0:
            raise ValueError(f"theme_id={item['theme_id']} 노름 0")
        raw.append(v)
        metas.append({
            "theme_id": int(item["theme_id"]),
            "field_id": int(item["field_id"]),
            "code": str(item["code"]),
            "name": str(item["name"]),
        })

    mat = np.stack(raw, axis=0)
    # 이 파일(=DB) 의 임베딩은 노름 1.0 로 저장돼 있다. centroid 도 정규화 공간의
    # 평균이므로 그대로 빼면 된다. 만약 다른 노름으로 저장된 카탈로그가 오면
    # 여기서 먼저 정규화해야 한다.
    if centroid is not None:
        nn = np.linalg.norm(mat, axis=1, keepdims=True)
        nn[nn == 0] = 1.0
        mat = mat / nn - centroid
    n = np.linalg.norm(mat, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return mat / n, metas


def catalog_health(mat: np.ndarray, metas: list[dict]) -> None:
    """중심화 여부를 진단한다. worker 쪽 문제를 여기서 먼저 잡는다."""
    mu = mat.mean(axis=0)
    norm = float(np.linalg.norm(mu))
    S = mat @ mat.T
    np.fill_diagonal(S, -9)
    fid = np.array([m["field_id"] for m in metas])
    same = fid[:, None] == fid[None, :]
    eye = np.eye(len(metas), dtype=bool)
    sf = float(S[same & ~eye].mean())
    cf = float(S[~same].mean())
    top2 = np.sort(S, axis=1)[:, ::-1][:, :2]
    margins = top2[:, 0] - top2[:, 1]

    print("  카탈로그 진단")
    print(f"    ||mean||            {norm:.4f}   (0.3 미만 정상 / 0.7 초과 = 중심화 안 됨)")
    print(f"    같은 분야 코사인     {sf:+.4f}")
    print(f"    다른 분야 코사인     {cf:+.4f}")
    print(f"    분리 신호           {sf - cf:+.4f}   (0.10 이상 권장)")
    print(f"    1위-2위 마진 중앙값  {np.median(margins):.4f}   (0.03 이상 권장)")
    if norm > 0.7:
        print("    >>> 경고: 중심화되지 않은 카탈로그입니다.")
        print("        분야 판정이 소수점 셋째 자리로 갈려 버킷이 뒤섞입니다.")
        print("        worker 쪽 중심화를 먼저 적용하고 카탈로그를 재생성하세요.")


# =====================================================================
# 임베딩 — worker 의 create_article_embedding 을 그대로 쓴다
#   본문을 4000자로 잘라 한 번에 인코딩하는 방식은 worker 와 다른 벡터를 만든다.
#   worker 는 제목을 모든 청크에 넣고 384 토큰씩 겹쳐 자른 뒤 가중 평균한다.
#   자세한 이유는 worker_embed.py 의 docstring 참고.
# =====================================================================
def center(vectors: np.ndarray, centroid: np.ndarray | None) -> np.ndarray:
    """단위벡터에서 centroid 를 빼고 다시 정규화한다.

    worker classifier.py 의 _center() 와 같은 연산이어야 한다.
    """
    if centroid is not None:
        vectors = vectors - centroid
    n = np.linalg.norm(vectors, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return (vectors / n).astype(np.float32)


# =====================================================================
def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="앞에서 N건만")
    args = ap.parse_args()

    cfg = load_config()
    fields = {int(k): v for k, v in cfg.fields.items()} \
        if isinstance(cfg.fields, dict) else dict(enumerate(cfg.fields, 1))

    src = work_path(cfg, "clean.jsonl")
    dst = work_path(cfg, "clean.field.jsonl")

    rows = list(read_jsonl(src))
    if args.limit and args.limit < len(rows):
        # 앞에서 자르면 특정 시간대·요일에 쏠린다. 무작위 표본을 쓴다.
        import random
        rows = random.Random(42).sample(rows, args.limit)
    print(f"입력 {len(rows):,}건  ({src})")

    centroid = None
    cpath = getattr(cfg.assign, "centroid", "")
    if cpath:
        cp = Path(cpath).expanduser()
        if cp.exists():
            centroid = np.load(cp).astype(np.float32)
            print(f"centroid 적용: {cp} (노름 {np.linalg.norm(centroid):.4f})")
        else:
            print(f"[경고] centroid 파일 없음: {cp} — 중심화 없이 진행")
    else:
        print("centroid 미설정 — 중심화 없이 진행 "
              "(python -m distill.build_centroid 로 만들 수 있습니다)")

    mat, metas = load_catalog(cfg.assign.catalog, centroid)
    print(f"카탈로그 테마 {len(metas)}개 / 분야 {sorted({m['field_id'] for m in metas})}")
    catalog_health(mat, metas)

    from .worker_embed import encode_articles
    raw, kept = encode_articles(rows, cfg.assign.worker_path,
                                cfg.assign.embed_batch_size)
    if len(kept) < len(rows):
        print(f"  [주의] 제목·본문이 비어 임베딩하지 못한 기사 "
              f"{len(rows) - len(kept):,}건을 건너뜁니다")
    rows = [rows[i] for i in kept]
    emb = center(raw, centroid)

    sims = emb @ mat.T                       # (N, 68)
    order = np.argsort(sims, axis=1)[:, ::-1]
    top1 = order[:, 0]
    top2 = order[:, 1]
    best = sims[np.arange(len(rows)), top1]
    second = sims[np.arange(len(rows)), top2]
    margin = best - second

    min_margin = float(getattr(cfg.assign, "min_margin", 0.0) or 0.0)
    stats = collections.Counter()
    out = []
    for i, r in enumerate(rows):
        m = metas[int(top1[i])]
        r = dict(r)
        r["theme_id"] = m["theme_id"]
        r["theme_code"] = m["code"]
        r["field_id"] = m["field_id"]
        r["field"] = fields[m["field_id"]]
        r["theme_similarity"] = round(float(best[i]), 4)
        r["theme_margin"] = round(float(margin[i]), 4)
        r["low_confidence"] = bool(margin[i] < min_margin) if min_margin else False
        if r["low_confidence"]:
            stats["low_confidence"] += 1
            continue                        # 학습셋에서만 제외. 서빙은 전부 처리.
        out.append(r)
        stats[r["field"]] += 1

    write_jsonl(dst, out)

    print(f"\n출력 {len(out):,}건  → {dst}")
    if min_margin:
        print(f"  마진 {min_margin} 미만으로 제외: {stats['low_confidence']:,}건")

    print("\n=== 분야 × 언어 ===")
    langs = sorted({r["lang"] for r in out})
    cross = collections.Counter((r["field"], r["lang"]) for r in out)
    print(f"  {'분야':<10}" + "".join(f"{l:>8}" for l in langs) + f"{'합계':>9}")
    for fid in sorted(fields):
        name = fields[fid]
        row = [cross[(name, l)] for l in langs]
        print(f"  {name:<10}" + "".join(f"{v:>8,}" for v in row) + f"{sum(row):>9,}")
    print(f"  {'합계':<10}" + "".join(
        f"{sum(cross[(fields[f], l)] for f in fields):>8,}" for l in langs))

    print("\n  (학습 400건 기준 수집 필요량 = 571건. 위 표에서 571 미만인 칸이 병목)")
    thin = [(f, l, cross[(f, l)]) for f in fields.values() for l in langs
            if cross[(f, l)] < 571]
    if thin:
        print("  얇은 칸:")
        for f, l, n in sorted(thin, key=lambda x: x[2]):
            print(f"    {f:<10}{l}  {n:,}")
    else:
        print("  모든 칸 충족")

    print("\n=== 테마 상위 15 ===")
    tc = collections.Counter(r["theme_code"] for r in out)
    for code, n in tc.most_common(15):
        print(f"  {n:>7,}  {code}")
    print(f"  (사용된 테마 {len(tc)}/68개)")


if __name__ == "__main__":
    main()
