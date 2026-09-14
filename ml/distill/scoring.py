"""확률 → 집계 → 라벨. 학습 대상이 아닌 순수 로직.

teacher 의 청크별 확률을 기사 하나의 값으로 합치고,
(P긍정, P부정) 두 확률에서 라벨과 0~100 점수를 만든다.

student 는 이 파일의 aggregate() 결과를 학습 타깃으로 받는다.
decide_label / tone_point 는 저장된 확률로 나중에 다시 계산할 수 있으므로,
임계값이 바뀌어도 재학습이 필요 없다.
"""
from __future__ import annotations

from typing import Literal

import numpy as np

ToneLabel = Literal["positive", "negative", "neutral", "mixed"]


def aggregate(
    probs: np.ndarray,          # (n_chunks, 2) — 열 0 = P긍정, 열 1 = P부정
    lengths: np.ndarray,        # (n_chunks,)   — 청크 토큰 수
    method: str = "weighted_mean",
    topk: int = 3,
) -> tuple[float, float]:
    """청크별 확률을 기사 단위 (P긍정, P부정) 로 합친다."""
    if probs.shape[0] == 0:
        return 0.0, 0.0

    if method == "weighted_mean":
        # 긴 청크가 더 많이 말한다 — 기사 전체 기조
        w = lengths.astype(np.float64)
        w = w / max(w.sum(), 1e-9)
        agg = (probs * w[:, None]).sum(axis=0)

    elif method == "max":
        # 가장 강한 극성 — 격한 한 줄에 민감
        agg = probs.max(axis=0)

    elif method == "topk_mean":
        # 극성이 뚜렷한 청크 상위 k개 평균 — 배경 설명은 무시, 한 줄에는 안 휘둘림
        strength = np.abs(probs[:, 0] - probs[:, 1])
        k = min(topk, probs.shape[0])
        idx = np.argsort(strength)[::-1][:k]
        agg = probs[idx].mean(axis=0)

    else:
        raise ValueError(f"알 수 없는 집계 방식: {method}")

    return float(agg[0]), float(agg[1])


def decide_label(
    p_pos: float, p_neg: float, mixed_threshold: float, neutral_threshold: float
) -> ToneLabel:
    """두 확률 → 라벨 4종.

    작은 쪽이 임계값 이상 → 둘 다 높다 → mixed
    큰 쪽이 임계값 미만  → 둘 다 낮다 → neutral
    """
    if min(p_pos, p_neg) >= mixed_threshold:
        return "mixed"
    if max(p_pos, p_neg) < neutral_threshold:
        return "neutral"
    return "positive" if p_pos > p_neg else "negative"


def tone_point(p_pos: float, p_neg: float) -> float:
    """(P긍정 − P부정) 을 0~100 으로. 50 = 중립 또는 혼합."""
    return round(50.0 * (1.0 + p_pos - p_neg), 2)
