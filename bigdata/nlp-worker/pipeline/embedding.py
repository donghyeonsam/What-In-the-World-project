"""
기사 임베딩 생성 모듈.

multilingual-e5-base 모델을 이용해 다국어 뉴스 기사를 임베딩한다.

긴 기사는 token 단위로 여러 chunk로 나누고,
각 chunk의 임베딩을 가중 평균하여
기사 전체를 대표하는 하나의 768차원 벡터를 생성한다.
"""

import numpy as np
import torch
from sentence_transformers import SentenceTransformer


# =========================================================
# Model
# =========================================================

MODEL_NAME = "intfloat/multilingual-e5-base"

MODEL_MAX_TOKENS = 512

# 실제 본문 chunk 크기
BODY_CHUNK_TOKENS = 384

# chunk 사이 문맥 보존
BODY_CHUNK_OVERLAP = 64

# 지나치게 긴 제목 제한
TITLE_MAX_TOKENS = 96

# 한 번에 GPU로 처리할 chunk 개수
ENCODE_BATCH_SIZE = 16


DEVICE = (
    "cuda"
    if torch.cuda.is_available()
    else "cpu"
)


# NLP Worker 시작 시 모델을 한 번만 로드한다.
_embedding_model = SentenceTransformer(
    MODEL_NAME,
    device=DEVICE,
)

_tokenizer = _embedding_model.tokenizer


# =========================================================
# Text
# =========================================================

def _normalize_text(text):
    """
    불필요한 줄바꿈과 연속 공백을 제거한다.
    """
    return " ".join(
        (text or "").split()
    )


def _text_to_token_ids(text):
    """
    긴 문자열도 잘리지 않도록 전체 token id를 반환한다.

    tokenizer.encode()를 긴 본문에 직접 사용했을 때 발생하는
    512 token 초과 경고를 피하기 위해 tokenize 후 변환한다.
    """
    tokens = _tokenizer.tokenize(text)

    return _tokenizer.convert_tokens_to_ids(
        tokens
    )


def _truncate_title(title):
    """
    제목이 지나치게 긴 경우 token 기준으로 제한한다.
    """
    title = _normalize_text(title)

    if not title:
        return ""

    token_ids = _text_to_token_ids(title)

    if len(token_ids) <= TITLE_MAX_TOKENS:
        return title

    token_ids = token_ids[
        :TITLE_MAX_TOKENS
    ]

    return _tokenizer.decode(
        token_ids,
        skip_special_tokens=True,
    ).strip()


# =========================================================
# Chunk
# =========================================================

def _build_chunk_inputs(title, body):
    """
    기사 본문을 token 단위로 여러 chunk로 분할한다.

    모든 chunk에 제목을 포함하여
    기사의 중심 주제가 유지되도록 한다.

    반환:
        inputs
            E5 모델 입력 문자열

        weights
            각 chunk가 새롭게 포함하는 body token 개수
    """

    title = _truncate_title(title)
    body = _normalize_text(body)

    # E5에서는 clustering에 query prefix 사용
    if title:
        prefix = f"query: {title}\n"
    else:
        prefix = "query: "

    # 제목과 본문이 모두 없는 경우
    if not title and not body:
        return [], []

    # 본문이 없는 경우 제목만 임베딩
    if not body:
        return [
            f"query: {title}"
        ], [1]

    prefix_token_count = len(
        _text_to_token_ids(prefix)
    )

    special_token_count = (
        _tokenizer.num_special_tokens_to_add(
            pair=False
        )
    )

    # 512 token을 넘지 않도록
    # 본문에 사용할 수 있는 최대 공간 계산
    available_body_tokens = (
            MODEL_MAX_TOKENS
            - prefix_token_count
            - special_token_count
    )

    if available_body_tokens <= 0:
        return [
            f"query: {title}"
        ], [1]

    chunk_size = min(
        BODY_CHUNK_TOKENS,
        available_body_tokens,
    )

    overlap = min(
        BODY_CHUNK_OVERLAP,
        chunk_size // 4,
        )

    if overlap >= chunk_size:
        overlap = 0

    body_token_ids = _text_to_token_ids(
        body
    )

    inputs = []
    weights = []

    start = 0
    previous_end = 0

    while start < len(body_token_ids):
        end = min(
            start + chunk_size,
            len(body_token_ids),
            )

        chunk_token_ids = body_token_ids[
            start:end
        ]

        chunk_text = _tokenizer.decode(
            chunk_token_ids,
            skip_special_tokens=True,
        ).strip()

        if chunk_text:
            inputs.append(
                f"{prefix}{chunk_text}"
            )

            # overlap된 영역은 이미 이전 chunk에서
            # 반영했으므로 신규 token만 가중치로 사용
            unique_token_count = (
                    end
                    - max(
                start,
                previous_end,
            )
            )

            weights.append(
                max(
                    unique_token_count,
                    1,
                )
            )

        previous_end = max(
            previous_end,
            end,
        )

        if end >= len(body_token_ids):
            break

        start = end - overlap

    return inputs, weights


# =========================================================
# Pooling
# =========================================================

def _pool_chunk_embeddings(
        embeddings,
        weights,
):
    """
    여러 chunk embedding을 하나의 article embedding으로 합친다.

    신규 token 수를 가중치로 사용하여
    overlap 영역이 과도하게 반영되지 않도록 한다.
    """

    embeddings = np.asarray(
        embeddings,
        dtype=np.float32,
    )

    # chunk 하나면 그대로 반환
    if (embeddings.ndim != 2 or embeddings.shape[1] != 768
            or len(embeddings) == 0 or not np.all(np.isfinite(embeddings))
            or np.any(np.linalg.norm(embeddings, axis=1) == 0)):
        raise RuntimeError("Embedding model must return finite, non-zero 768D vectors")
    if (len(weights) != len(embeddings) or not np.all(np.isfinite(weights))
            or np.any(np.asarray(weights) <= 0)):
        raise RuntimeError("Invalid embedding aggregation weights")
    if len(embeddings) == 1:
        return embeddings[0]

    weights = np.asarray(
        weights,
        dtype=np.float32,
    )

    pooled = np.average(
        embeddings,
        axis=0,
        weights=weights,
    )

    # 평균 후 다시 L2 normalize
    norm = np.linalg.norm(pooled)

    if not np.isfinite(norm) or norm == 0:
        raise RuntimeError("Pooled article embedding is zero or non-finite")
    pooled = pooled / norm

    return pooled.astype(
        np.float32
    )


# =========================================================
# Public
# =========================================================

def create_summary_embedding(summary):
    """요약문 하나를 768차원 벡터로 만든다.

    create_article_embedding 과 '같은 벡터 공간'에 있어야 비교가 되므로
    prefix("query: ")와 normalize 설정을 반드시 맞춘다.
    E5 는 query/passage prefix 로 공간이 갈려서, 여기만 passage 를 쓰면
    숫자는 나오지만 코사인 유사도의 의미가 어긋난다.

    요약은 3문장(최대 400자)이라 512 token 을 넘지 않으므로 청킹하지 않는다.
    중심화(centering)도 하지 않는다. classifier 가 분류할 때만 centroid 를 빼고,
    저장되는 article_embedding 은 중심화 전 원본이기 때문이다.
    여기서 미리 빼면 되돌릴 수 없다.

    요약이 없으면(요약 실패) None 을 돌려준다.
    """

    text = _normalize_text(summary)

    if not text:
        return None

    embeddings = _embedding_model.encode(
        [f"query: {text}"],
        batch_size=1,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    embedding = np.asarray(
        embeddings,
        dtype=np.float32,
    )

    # create_article_embedding 과 동일한 수준으로 출력을 검증한다.
    if (embedding.ndim != 2
            or embedding.shape != (1, 768)
            or not np.all(np.isfinite(embedding))
            or np.linalg.norm(embedding[0]) == 0):
        raise RuntimeError(
            "Embedding model must return a finite, non-zero 768D vector"
        )

    # Kafka JSON 직렬화를 위해 list로 변환
    return embedding[0].tolist()


def create_article_embedding(article):
    """
    title과 body 전체를 이용하여
    하나의 768차원 article embedding을 생성한다.
    """

    title = article.get(
        "title",
        "",
    ) or ""

    body = article.get(
        "body",
        "",
    ) or ""

    inputs, weights = _build_chunk_inputs(
        title,
        body,
    )

    if not inputs:
        return None

    # 여러 chunk를 batch 단위로 GPU에서 처리
    embeddings = _embedding_model.encode(
        inputs,
        batch_size=ENCODE_BATCH_SIZE,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    article_embedding = (
        _pool_chunk_embeddings(
            embeddings,
            weights,
        )
    )

    # Kafka JSON 직렬화를 위해 list로 변환
    return article_embedding.tolist()