"""
기사 임베딩을 68개 theme 임베딩과 비교해 가장 가까운 theme를 찾는 모듈.

- theme_catalog.json은 resources/ 디렉토리에서 읽는다.
- theme embedding은 NLP Worker 시작 후 메모리에 캐싱한다.
- cosine similarity를 사용한다.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np


EMBEDDING_DIMENSION = 768

# pipeline/classifier.py -> nlp-worker/resources/theme_catalog.json
DEFAULT_CATALOG_PATH = (
    Path(__file__).resolve().parent.parent
    / "resources"
    / "theme_catalog.json"
)


class ThemeClassifier:
    """theme_catalog.json을 메모리에 올려 기사 임베딩과 비교한다."""

    def __init__(self, catalog_path: str | Path = DEFAULT_CATALOG_PATH) -> None:
        self.catalog_path = Path(catalog_path)
        self.themes: list[dict[str, Any]] = []
        self.theme_matrix: np.ndarray

        self._load_catalog()

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
        """
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

        vector = vector / norm

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

        vector = vector / norm
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
