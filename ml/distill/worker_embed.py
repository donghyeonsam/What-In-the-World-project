"""worker 의 임베딩 함수를 그대로 불러다 쓴다.

왜 복사하지 않고 import 하나
  학습 때 기사를 분야로 나누는 기준과, 런타임에 기사를 어느 톤 모델로 보낼지
  정하는 기준이 같아야 한다. 그래서 worker 의 ThemeClassifier 를 재사용하기로
  했는데, 정작 그 앞단인 '임베딩을 어떻게 만드느냐' 가 다르면 소용이 없다.

  worker 의 create_article_embedding 은
    · 제목을 모든 청크에 반복해서 넣고
    · 본문을 384 토큰씩 64 겹쳐 자르고
    · 신규 토큰 수로 가중 평균한 뒤 재정규화한다
  본문 4000자를 한 번에 인코딩하는 것과는 다른 벡터가 나온다.

  코드를 베껴 오면 worker 가 바뀔 때 조용히 어긋난다. 파일을 직접 읽어
  쓰면 그런 드리프트가 생길 수 없다.

왜 패키지를 import 하지 않나
  `import pipeline.embedding` 은 pipeline/__init__.py 를 먼저 실행하고, 그러면
  GLiNER·fastText·톤 teacher 까지 전부 메모리에 올라온다. 임베딩만 필요하므로
  embedding.py 파일 하나만 단독 로드한다 (이 파일은 numpy·torch·
  sentence_transformers 만 import 하므로 단독 로드가 가능하다).

배치 처리
  worker 는 기사를 한 건씩 처리한다. 12만 건을 그렇게 돌리면 느리다.
  encode_articles() 는 여러 기사의 청크를 모아 한 번에 인코딩한다.
  인코딩은 시퀀스끼리 독립이므로 결과는 한 건씩 돌린 것과 같다.
  청크 분할과 풀링은 worker 함수를 그대로 호출한다.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np

_module = None


def load_worker_embedding(worker_path: str | Path):
    """nlp-worker/pipeline/embedding.py 를 단독 모듈로 로드한다."""
    global _module
    if _module is not None:
        return _module

    root = Path(worker_path).expanduser()
    path = root / "pipeline" / "embedding.py"

    if not path.exists():
        sys.exit(
            f"worker 임베딩 모듈을 찾을 수 없습니다: {path}\n"
            f"config.yaml 의 assign.worker_path 를 확인하세요 "
            f"(현재값: {worker_path})"
        )

    spec = importlib.util.spec_from_file_location("_worker_embedding", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    print(f"  worker 임베딩 로드: {path}")
    print(f"    모델          {module.MODEL_NAME}")
    print(f"    device        {module.DEVICE}")
    print(f"    청크 토큰     {module.BODY_CHUNK_TOKENS} (겹침 {module.BODY_CHUNK_OVERLAP})")
    print(f"    제목 상한     {module.TITLE_MAX_TOKENS} 토큰")

    _module = module
    return module


def encode_articles(articles: list[dict], worker_path: str | Path,
                    batch_size: int = 128) -> tuple[np.ndarray, list[int]]:
    """기사 리스트를 worker 와 동일한 방식으로 임베딩한다.

    반환
        (N x 768 행렬, 임베딩에 성공한 기사의 원본 인덱스 리스트)

    제목·본문이 모두 비어 청크가 하나도 안 나오는 기사는 건너뛴다.
    worker 도 그 경우 None 을 돌려주고 process_article 이 예외를 던진다.
    """
    module = load_worker_embedding(worker_path)

    # ---- 1) 기사별 청크 만들기 (worker 함수 그대로) ----------------------
    all_chunks: list[str] = []
    spans: list[tuple[int, int, list[int]]] = []   # (기사 인덱스, 시작, 가중치)
    kept: list[int] = []

    for i, article in enumerate(articles):
        inputs, weights = module._build_chunk_inputs(
            article.get("title", "") or "",
            article.get("body", "") or "",
        )
        if not inputs:
            continue
        spans.append((i, len(all_chunks), weights))
        all_chunks.extend(inputs)
        kept.append(i)

        if (i + 1) % 20000 == 0:
            print(f"    청크 분할 {i + 1:>7,}/{len(articles):,}", flush=True)

    if not all_chunks:
        return np.zeros((0, 768), dtype=np.float32), []

    print(f"    기사 {len(kept):,}건 → 청크 {len(all_chunks):,}개 "
          f"(기사당 평균 {len(all_chunks) / max(len(kept), 1):.1f}개)")

    # ---- 2) 청크를 한꺼번에 인코딩 ---------------------------------------
    chunk_vectors = np.empty((len(all_chunks), 768), dtype=np.float32)

    for start in range(0, len(all_chunks), batch_size):
        end = min(start + batch_size, len(all_chunks))
        chunk_vectors[start:end] = module._embedding_model.encode(
            all_chunks[start:end],
            batch_size=batch_size,
            normalize_embeddings=True,      # worker 와 동일
            convert_to_numpy=True,
            show_progress_bar=False,
        ).astype(np.float32)

        if (start // batch_size) % 50 == 0:
            print(f"    인코딩 {end:>8,}/{len(all_chunks):,}", flush=True)

    # ---- 3) 기사 단위로 풀링 (worker 함수 그대로) ------------------------
    out = np.empty((len(spans), 768), dtype=np.float32)

    for row, (_, start, weights) in enumerate(spans):
        out[row] = module._pool_chunk_embeddings(
            chunk_vectors[start:start + len(weights)],
            weights,
        )

    return out, kept
