"""
기사 임베딩을 68개 theme 임베딩과 비교해 가장 가까운 theme를 찾는 모듈.

- theme_catalog.json은 resources/ 디렉토리에서 읽는다.
- theme embedding은 NLP Worker 시작 후 메모리에 캐싱한다.
- cosine similarity를 사용한다.
- resources/centroid.npy 가 있으면 '중심화'를 적용한다. 아래 참고.

중심화(mean-centering)란
  E5 임베딩은 이방성(anisotropy)이 심하다. 실측으로 전체 기사 임베딩 평균의
  크기가 0.9207 이었다. 즉 모든 벡터가 한 방향으로 쏠려 있고, 서로 다른 분야의
  테마끼리도 cosine 이 +0.8409 나온다. 그 결과 1위와 2위 테마의 마진이 0.0051
  밖에 안 되어(68개 중 50개가 0.01 미만) 분야가 거의 무작위로 갈렸다.

  공통 성분(centroid)을 빼고 다시 정규화하면 남는 것은 기사마다 다른 성분뿐이다.
  실측 개선: 테마 마진 0.0051 → 0.0254(5.0배), 분야 마진 0.0466(9.1배),
  실제로 쓰인 테마 61개 → 68개, 독일어 POLITICS 쏠림 52.9% → 23.9%
  (실제 섹션 비율 21.8%).

  DB 도, theme_catalog.json 도 건드리지 않는다. 로드한 뒤 메모리에서만 뺀다.
  centroid.npy 가 없으면 기존과 100% 동일하게 동작한다(행렬이 비트 단위로 같다).

주의
  중심화를 켜면 similarity 값의 범위 자체가 바뀐다(0.85대 → 0.25대).
  theme_relevance_score 를 임계값으로 거르는 하류 로직이 있다면 같이 조정해야 한다.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

EMBEDDING_DIMENSION = 768

# pipeline/classifier.py -> nlp-worker/resources/theme_catalog.json
DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parent.parent
    / "resources"
    / "theme_catalog.json"
)

# pipeline/classifier.py -> nlp-worker/resources/centroid.npy
# 파일이 없으면 중심화를 하지 않는다(기존 동작 그대로). 롤백은 파일을 치우면 끝.
DEFAULT_CENTROID_PATH = Path(
    os.getenv(
        "THEME_CENTROID_PATH",
        str(Path(__file__).resolve().parent.parent / "resources" / "centroid.npy"),
    )
)


class ThemeClassifier:
    """theme_catalog.json을 메모리에 올려 기사 임베딩과 비교한다."""

    def __init__(
        self,
        catalog_path: str | Path = DEFAULT_CATALOG_PATH,
        centroid_path: str | Path | None = DEFAULT_CENTROID_PATH,
    ) -> None:
        self.catalog_path = Path(catalog_path)
        self.centroid_path = Path(centroid_path) if centroid_path else None
        self.themes: list[dict[str, Any]] = []
        self.theme_matrix: np.ndarray

        # 카탈로그를 읽기 '전에' centroid 를 올려야 한다.
        # _load_catalog 안에서 테마 임베딩에도 같은 중심화를 적용하기 때문이다.
        self.centroid = self._load_centroid()
        self._load_catalog()

    def _load_centroid(self) -> np.ndarray | None:
        """resources/centroid.npy 를 읽는다. 없으면 None(= 중심화 안 함)."""
        if self.centroid_path is None or not self.centroid_path.exists():
            logger.warning(
                "centroid not found (%s); theme classification runs WITHOUT "
                "centering. 1위-2위 마진이 0.005 수준이라 분야가 거의 무작위로 "
                "갈립니다.",
                self.centroid_path,
            )
            return None

        centroid = np.asarray(np.load(self.centroid_path), dtype=np.float32).ravel()

        if centroid.shape != (EMBEDDING_DIMENSION,):
            raise ValueError(
                f"centroid dimension is {centroid.shape}, "
                f"expected ({EMBEDDING_DIMENSION},): {self.centroid_path}"
            )
        if not np.all(np.isfinite(centroid)):
            raise ValueError(f"centroid contains NaN or Infinity: {self.centroid_path}")

        logger.info(
            "Theme centering enabled: %s (||centroid||=%.4f)",
            self.centroid_path,
            float(np.linalg.norm(centroid)),
        )
        return centroid

    def _center(self, vector: np.ndarray) -> np.ndarray:
        """공통 성분을 빼고 다시 단위벡터로 만든다.

        반드시 '정규화된' 벡터에 적용해야 한다. centroid 자체가 정규화된
        임베딩들의 평균으로 만들어졌기 때문이다. 정규화 전 벡터에서 빼면
        크기가 큰 기사일수록 덜 빠져 중심화가 반만 걸린다.
        """
        if self.centroid is None:
            return vector

        centered = vector - self.centroid
        norm = float(np.linalg.norm(centered))
        # centroid 와 거의 같은 방향인 벡터는 빼고 나면 0에 가까워진다.
        # 그럴 때는 나누지 말고 원본을 쓴다(0으로 나누면 NaN).
        if not np.isfinite(norm) or norm == 0.0:
            return vector
        return (centered / norm).astype(np.float32)

    def _prepare_vector(self, article_embedding: list[float] | np.ndarray) -> np.ndarray:
        """기사 임베딩 검증 → 정규화 → 중심화. classify 계열이 공통으로 쓴다."""
        vector = np.asarray(article_embedding, dtype=np.float32)

        if vector.shape != (EMBEDDING_DIMENSION,):
            raise ValueError(
                f"Article embedding dimension is {vector.shape}, "
                f"expected ({EMBEDDING_DIMENSION},)"
            )

        if not np.all(np.isfinite(vector)):
            raise ValueError(
                "Article embedding contains NaN or Infinity."
            )

        norm = np.linalg.norm(vector)
        if norm == 0:
            raise ValueError("Article embedding norm is 0.")

        return self._center(vector / norm)

    def _load_catalog(self) -> None:
        """카탈로그를 읽고 검증한 뒤 68 x 768 행렬로 캐싱한다."""
        if not self.catalog_path.exists():
            raise FileNotFoundError(
                f"theme catalog not found: {self.catalog_path}"
            )

        with self.catalog_path.open("r", encoding="utf-8") as f:
            catalog = json.load(f)

        if not isinstance(catalog, list):
            raise ValueError("theme_catalog.json root must be a list.")

        if len(catalog) != 68:
            raise ValueError(
                f"Expected 68 themes, but found {len(catalog)}."
            )

        theme_ids: set[int] = set()
        theme_codes: set[str] = set()
        embeddings: list[np.ndarray] = []

        for item in catalog:
            required_keys = {
                "theme_id",
                "field_id",
                "code",
                "name",
                "description",
                "embedding",
            }

            missing = required_keys - item.keys()
            if missing:
                raise ValueError(
                    f"Theme item is missing keys: {sorted(missing)}"
                )

            theme_id = int(item["theme_id"])
            code = str(item["code"])
            embedding = np.asarray(item["embedding"], dtype=np.float32)

            if theme_id in theme_ids:
                raise ValueError(f"Duplicate theme_id: {theme_id}")

            if code in theme_codes:
                raise ValueError(f"Duplicate theme code: {code}")

            if embedding.shape != (EMBEDDING_DIMENSION,):
                raise ValueError(
                    f"theme_id={theme_id} embedding dimension "
                    f"is {embedding.shape}, expected ({EMBEDDING_DIMENSION},)"
                )

            if not np.all(np.isfinite(embedding)):
                raise ValueError(
                    f"theme_id={theme_id} embedding contains NaN or Infinity."
                )

            norm = np.linalg.norm(embedding)
            if norm == 0:
                raise ValueError(
                    f"theme_id={theme_id} embedding norm is 0."
                )

            # 혹시 DB/JSON 값이 미세하게 정규화에서 벗어나더라도 안전하게 재정규화
            embedding = embedding / norm

            # 기사 쪽과 '같은' 중심화를 테마 쪽에도 적용한다.
            # 한쪽만 중심화하면 두 벡터가 다른 공간에 있게 되어 cosine 이 무의미해진다.
            embedding = self._center(embedding)

            theme_ids.add(theme_id)
            theme_codes.add(code)

            # 분류 결과에 embedding 자체는 필요 없으므로 메타데이터만 보관
            self.themes.append(
                {
                    "theme_id": theme_id,
                    "field_id": int(item["field_id"]),
                    "code": code,
                    "name": str(item["name"]),
                    "description": str(item["description"]),
                }
            )
            embeddings.append(embedding)

        self.theme_matrix = np.stack(embeddings, axis=0)

    def classify(self, article_embedding: list[float] | np.ndarray) -> dict[str, Any]:
        """
        기사 임베딩과 모든 theme의 cosine similarity를 비교해 Top-1을 반환한다.

        반환 예:
        {
            "theme_id": 1,
            "field_id": 1,
            "code": "election",
            "name": "선거",
            "similarity": 0.8123
        }

        주의: centroid.npy 가 적용되면 similarity 범위가 0.85대에서 0.25대로
        내려간다. 값이 작아진 것이지 나빠진 것이 아니다. 공통 성분(모든 기사가
        공유해 변별력이 없는 부분)이 빠졌기 때문이다.
        """
        vector = self._prepare_vector(article_embedding)

        # 두 벡터가 정규화되어 있으므로 dot product == cosine similarity
        similarities = self.theme_matrix @ vector

        best_index = int(np.argmax(similarities))
        best_theme = self.themes[best_index]

        return {
            **best_theme,
            "similarity": float(similarities[best_index]),
        }

    def classify_top_k(
        self,
        article_embedding: list[float] | np.ndarray,
        k: int = 3,
    ) -> list[dict[str, Any]]:
        """테스트/검증용으로 similarity가 높은 theme Top-K를 반환한다."""
        if k < 1:
            raise ValueError("k must be >= 1")

        vector = self._prepare_vector(article_embedding)
        similarities = self.theme_matrix @ vector

        k = min(k, len(self.themes))
        top_indices = np.argsort(similarities)[::-1][:k]

        return [
            {
                **self.themes[int(index)],
                "similarity": float(similarities[int(index)]),
            }
            for index in top_indices
        ]


_classifier: ThemeClassifier | None = None


def get_theme_classifier() -> ThemeClassifier:
    """
    ThemeClassifier singleton을 반환한다.

    main.py에서 기사마다 새로 생성하지 않고,
    최초 1회만 theme_catalog.json을 메모리에 로드하기 위한 함수다.
    """
    global _classifier

    if _classifier is None:
        _classifier = ThemeClassifier()

    return _classifier


def classify_theme(
    article_embedding: list[float] | np.ndarray,
) -> dict[str, Any]:
    """main.py에서 간단히 호출하기 위한 래퍼 함수."""
    return get_theme_classifier().classify(article_embedding)