"""청크 → 기사 집계, 라벨 판정, 톤 점수. 순수 넘파이. 학습 대상이 아니다.

임계값은 학습되지 않는다. 저장된 확률에서 언제든 다시 계산된다.
바꾸고 싶으면 config.yaml만 고치면 되고 라벨링을 다시 돌릴 필요가 없다.
"""
from __future__ import annotations

import numpy as np

AGG_METHODS = ("weighted_mean", "max", "topk_mean")


def _as_arrays(p_pos, p_neg, lengths=None):
    a = np.asarray(p_pos, dtype=np.float64).ravel()
    b = np.asarray(p_neg, dtype=np.float64).ravel()
    if a.shape != b.shape:
        raise ValueError(f"청크 수 불일치: p_pos {a.shape} vs p_neg {b.shape} "
                         "(청크는 한 번만 쪼개서 두 축이 공유해야 함)")
    if lengths is None:
        w = np.ones_like(a)
    else:
        w = np.asarray(lengths, dtype=np.float64).ravel()
        if w.shape != a.shape:
            raise ValueError(f"lengths 길이 불일치: {w.shape} vs {a.shape}")
    return a, b, w


def agg_weighted_mean(p_pos, p_neg, lengths=None) -> tuple[float, float]:
    """길이 가중평균. 기사 전체를 대표하지만 중립 청크에 희석되고 편향이 누적된다."""
    a, b, w = _as_arrays(p_pos, p_neg, lengths)
    if a.size == 0:
        return 0.0, 0.0
    tot = w.sum()
    if tot <= 0:
        return float(a.mean()), float(b.mean())
    return float((a * w).sum() / tot), float((b * w).sum() / tot)


def agg_max(p_pos, p_neg, lengths=None) -> tuple[float, float]:
    """축별 최고값. 중립에 둔감하지만 두 축의 최고값이 서로 다른 청크에서 와서
    과하게 mixed로 판정된다."""
    a, b, _ = _as_arrays(p_pos, p_neg, lengths)
    if a.size == 0:
        return 0.0, 0.0
    return float(a.max()), float(b.max())


def agg_topk_mean(p_pos, p_neg, lengths=None, topk: int = 2) -> tuple[float, float]:
    """극성차 |p_pos - p_neg| 상위 k개 청크의 평균.

    청크를 '통째로' 고르기 때문에 두 축이 항상 같은 청크에서 온다.
    중립 청크가 0개든 16개든 결과가 같다. → 확정된 방식.
    """
    a, b, _ = _as_arrays(p_pos, p_neg, lengths)
    if a.size == 0:
        return 0.0, 0.0
    k = max(1, min(int(topk), a.size))
    diff = np.abs(a - b)
    # 동점일 때 앞 청크 우선 (결정적 정렬)
    order = np.lexsort((np.arange(a.size), -diff))[:k]
    return float(a[order].mean()), float(b[order].mean())


def aggregate(p_pos, p_neg, lengths=None, method: str = "topk_mean",
              topk: int = 2) -> tuple[float, float]:
    if method == "weighted_mean":
        return agg_weighted_mean(p_pos, p_neg, lengths)
    if method == "max":
        return agg_max(p_pos, p_neg, lengths)
    if method == "topk_mean":
        return agg_topk_mean(p_pos, p_neg, lengths, topk=topk)
    raise ValueError(f"알 수 없는 집계 방식: {method}")


def aggregate_all(p_pos, p_neg, lengths=None, topk: int = 2) -> dict[str, dict]:
    """3방식 전부 계산해서 alt_agg로 저장한다.

    teacher 추론이 끝난 뒤의 넘파이 산수라 비용이 0이다.
    나중에 사람 검증 라벨과 대조해 방식을 확정할 수 있다 (choose_aggregate.py).
    """
    out: dict[str, dict] = {}
    for m in AGG_METHODS:
        pp, pn = aggregate(p_pos, p_neg, lengths, method=m, topk=topk)
        out[m] = {"p_pos": round(pp, 6), "p_neg": round(pn, 6)}
    return out


def decide_label(p_pos: float, p_neg: float, mixed_threshold: float = 0.50,
                 neutral_threshold: float = 0.40) -> str:
    """확률 2개에서 라벨을 '로직으로' 판정한다. 학습 대상이 아니다."""
    if min(p_pos, p_neg) >= mixed_threshold:
        return "mixed"
    if max(p_pos, p_neg) < neutral_threshold:
        return "neutral"
    return "positive" if p_pos > p_neg else "negative"


def tone_point(p_pos: float, p_neg: float) -> float:
    """0~100 연속 논조 점수. DB article.tone_score에 저장된다.

    주의: mixed와 neutral은 tone_point가 같을 수 있다(둘 다 ~51.5).
    반드시 라벨을 점수와 함께 저장해야 구분된다.
    """
    return 50.0 * (1.0 + p_pos - p_neg)


def confidence(p_pos: float, p_neg: float) -> float:
    return float(max(p_pos, p_neg))


def make_sentiment(p_pos: float, p_neg: float, mixed_threshold: float = 0.50,
                   neutral_threshold: float = 0.40) -> dict:
    """NLP worker의 sentiment 필드 형태. label/score/confidence."""
    return {
        "label": decide_label(p_pos, p_neg, mixed_threshold, neutral_threshold),
        "score": round(tone_point(p_pos, p_neg), 4),
        "confidence": round(confidence(p_pos, p_neg), 6),
        "p_pos": round(float(p_pos), 6),
        "p_neg": round(float(p_neg), 6),
    }


# --- 진단값 -----------------------------------------------------------------
def neutral_baseline(p_pos, p_neg, band: float = 0.15,
                     low_conf: float = 0.50) -> dict:
    """중립 청크에서 두 축의 평균. 편향이 없으면 두 값이 같아야 한다.

    어긋나면 그 차이가 weighted_mean에서 중립 청크 수만큼 누적된다
    (축 기저율 비대칭).

    두 가지 기준을 함께 낸다.
      band  — |p_pos - p_neg| < band. 원래 정의지만 맹점이 있다:
              편향이 클수록(예: 0.15 vs 0.45, 차이 0.30) 그 청크가
              band 밖으로 밀려나 진단에서 빠진다. 정작 필요한 때 n=0이 된다.
      lowmax— max(p_pos, p_neg) < low_conf. 극성차와 무관하게
              '둘 다 약한' 청크를 잡으므로 강한 편향도 보인다.
    """
    a, b, _ = _as_arrays(p_pos, p_neg)

    def summarize(mask: np.ndarray) -> tuple[int, float | None, float | None, float | None]:
        n = int(mask.sum())
        if n == 0:
            return 0, None, None, None
        pos, neg = float(a[mask].mean()), float(b[mask].mean())
        return n, round(pos, 6), round(neg, 6), round(pos - neg, 6)

    n1, pos1, neg1, gap1 = summarize(np.abs(a - b) < band)
    n2, pos2, neg2, gap2 = summarize(np.maximum(a, b) < low_conf)
    return {"n": n1, "pos": pos1, "neg": neg1, "gap": gap1,
            "n_lowmax": n2, "pos_lowmax": pos2, "neg_lowmax": neg2,
            "gap_lowmax": gap2}


def hypothesis_disagreement(per_hyp: np.ndarray) -> float:
    """앙상블 가설끼리의 표준편차 평균.

    per_hyp: (n_chunks, n_hyp). 높으면 기사가 애매하거나 가설 문구에 문제가 있다.
    """
    arr = np.asarray(per_hyp, dtype=np.float64)
    if arr.size == 0 or arr.ndim != 2 or arr.shape[1] < 2:
        return 0.0
    return float(arr.std(axis=1, ddof=0).mean())
