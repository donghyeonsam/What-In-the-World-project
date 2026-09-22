"""[stage 0.4] centroid 계산 — work/clean.jsonl → work/centroid.npy

왜 필요한가
  multilingual-e5 임베딩은 비등방성(anisotropy)이 심하다. 모든 벡터가 고차원
  공간의 좁은 원뿔 안에 몰려 있어서, 아무 관계없는 두 텍스트도 코사인 유사도가
  0.85 근처로 나온다. 그 상태에서 68개 테마 중 최근접을 고르면 1위와 2위의
  차이가 소수점 셋째 자리라, 사실상 동전 던지기가 된다.

  코퍼스 평균(centroid)을 빼면 그 공통 성분이 사라지고 실제 의미 차이만 남는다.

무엇을 하나
  기사 표본 N건을 worker 의 create_article_embedding 과 동일한 방식으로
  임베딩해 평균을 구하고 work/centroid.npy 로 저장한다.
  worker 가 실제로 만들어내는 벡터들의 중심이어야 의미가 있다.

중요 1 — 양쪽에 적용
  이 centroid 는 기사와 테마 카탈로그 '양쪽에' 똑같이 적용해야 한다.
  한쪽만 중심화하면 서로 다른 공간의 벡터를 비교하게 돼 지금보다 나빠진다.
  assign_field.py 가 두 곳 모두에 적용한다.

중요 2 — worker 와 같은 파일
  런타임에 기사를 어느 톤 모델로 보낼지는 worker 가 정한다. worker 가 다른
  centroid 를 쓰면 학습 때 나눈 기준과 어긋난다.
  worker 쪽에 이미 resources/centroid.npy 가 있으면 그것을 복사해 쓰고,
  이 스크립트는 돌리지 않는다.

실행
    python -m distill.build_centroid
    python -m distill.build_centroid --sample 50000
"""
from __future__ import annotations

import argparse
import collections
import random
from pathlib import Path

import numpy as np

from .config import load_config, work_path
from .io_utils import read_jsonl


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=20000,
                    help="centroid 계산에 쓸 기사 수 (기본 20000)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    cfg = load_config()
    src = work_path(cfg, "clean.jsonl")
    dst = work_path(cfg, "centroid.npy")

    # worker 가 이미 centroid 를 갖고 있으면 그걸 써야 한다
    worker_centroid = (Path(cfg.assign.worker_path).expanduser()
                       / "resources" / "centroid.npy")
    if worker_centroid.exists():
        print(f"[주의] worker 쪽에 centroid 가 이미 있습니다:\n  {worker_centroid}")
        print("  학습과 서빙이 같은 centroid 를 써야 하므로, 새로 만들지 말고")
        print("  그 파일을 복사해 쓰세요:")
        print(f"    cp {worker_centroid} {dst}")
        print("  그래도 새로 만들려면 --force 를 붙이세요.")
        import sys
        if "--force" not in sys.argv:
            return

    rows = list(read_jsonl(src))
    print(f"입력 {len(rows):,}건")

    # 언어·시간대가 고루 섞이도록 무작위 표본
    rng = random.Random(args.seed)
    if len(rows) > args.sample:
        rows = rng.sample(rows, args.sample)
    print(f"표본 {len(rows):,}건으로 centroid 계산")
    print("  언어 구성:",
          dict(collections.Counter(r["lang"] for r in rows).most_common()))

    # worker 와 동일한 임베딩 경로. create_article_embedding 은 L2 정규화된
    # 벡터를 돌려주므로, 그 평균이 곧 정규화 공간의 중심이다.
    from .worker_embed import encode_articles
    vectors, kept = encode_articles(rows, cfg.assign.worker_path,
                                    cfg.assign.embed_batch_size)

    if len(vectors) == 0:
        raise SystemExit("임베딩된 기사가 없습니다.")

    centroid = vectors.astype(np.float64).mean(axis=0).astype(np.float32)
    np.save(dst, centroid)

    print(f"\n저장 {dst}")
    print(f"  사용 {len(kept):,}건 / 건너뜀 {len(rows) - len(kept):,}건")
    print(f"  차원 {centroid.shape[0]} / 노름 {np.linalg.norm(centroid):.4f}")
    print("\n  노름이 0.85~0.95 면 정상입니다 (비등방성이 그만큼 심하다는 뜻).")
    print("\n그다음  python -m distill.assign_field --limit 2000  으로 진단을 보세요.")
    print("worker 담당자에게도 이 파일을 넘겨 resources/centroid.npy 로 쓰게 하세요.")


if __name__ == "__main__":
    main()
