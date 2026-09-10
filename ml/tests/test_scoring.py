"""scoring.py 테스트. 순수 넘파이라 여기서도 돈다.

집계 방식 선택의 근거(축 기저율 비대칭)를 테스트로 고정해둔다.
나중에 누가 weighted_mean으로 되돌리면 이 테스트가 깨진다.
"""
from __future__ import annotations

import numpy as np
import pytest

from distill.scoring import (agg_max, agg_topk_mean, agg_weighted_mean,
                             aggregate, aggregate_all, decide_label,
                             hypothesis_disagreement, make_sentiment,
                             neutral_baseline, tone_point)


# --- decide_label -----------------------------------------------------------
@pytest.mark.parametrize("pp,pn,expected", [
    (0.88, 0.10, "positive"),
    (0.12, 0.85, "negative"),
    (0.30, 0.25, "neutral"),     # 둘 다 neutral_threshold 미만
    (0.70, 0.65, "mixed"),       # 둘 다 mixed_threshold 이상
    (0.55, 0.20, "positive"),
    (0.39, 0.39, "neutral"),
    (0.50, 0.50, "mixed"),       # 경계 포함
])
def test_decide_label(pp, pn, expected):
    assert decide_label(pp, pn) == expected


def test_mixed_and_neutral_can_share_tone_point():
    """mixed와 neutral의 tone_point가 같을 수 있다 → 라벨을 함께 저장해야 한다."""
    mixed = make_sentiment(0.72, 0.69)
    neutral = make_sentiment(0.33, 0.30)
    assert mixed["label"] == "mixed" and neutral["label"] == "neutral"
    assert mixed["score"] == neutral["score"] == pytest.approx(51.5)


def test_tone_point_range():
    assert tone_point(1.0, 0.0) == 100.0
    assert tone_point(0.0, 1.0) == 0.0
    assert tone_point(0.5, 0.5) == 50.0


def test_threshold_is_recomputable():
    """임계값은 학습되지 않는다. 저장된 확률에서 다시 계산된다."""
    pp, pn = 0.45, 0.44
    assert decide_label(pp, pn, neutral_threshold=0.40) == "positive"
    assert decide_label(pp, pn, neutral_threshold=0.50) == "neutral"


# --- 집계 3방식 -------------------------------------------------------------
def test_topk_mean_picks_whole_chunks():
    """두 축이 항상 같은 청크에서 온다."""
    pos = [0.88, 0.10, 0.12, 0.85]
    neg = [0.09, 0.20, 0.18, 0.11]
    pp, pn = agg_topk_mean(pos, neg, topk=2)          # 청크 0, 3 선택
    assert pp == pytest.approx((0.88 + 0.85) / 2)
    assert pn == pytest.approx((0.09 + 0.11) / 2)


def test_topk_mean_immune_to_neutral_chunk_count():
    """중립 청크가 0개든 16개든 결과가 같다."""
    pos, neg = [0.88, 0.85], [0.12, 0.15]
    base = agg_topk_mean(pos, neg, topk=2)
    for pad in (4, 8, 16):
        padded = agg_topk_mean(pos + [0.15] * pad, neg + [0.45] * pad, topk=2)
        assert padded == pytest.approx(base)


def test_weighted_mean_flips_on_axis_base_rate_asymmetry():
    """인계 문서의 그 예시. 명백한 긍정 기사가 negative로 뒤집힌다."""
    pos = [0.88, 0.85] + [0.15] * 8
    neg = [0.12, 0.15] + [0.45] * 8
    pp, pn = agg_weighted_mean(pos, neg)
    assert pp == pytest.approx(0.293, abs=1e-3)
    assert pn == pytest.approx(0.387, abs=1e-3)
    # 부정 축이 더 커진다(0.387 > 0.293). 기본 임계값에서는 두 축 모두
    # neutral_threshold 미만이라 최종 라벨이 neutral 로 떨어진다 —
    # 어느 쪽이든 명백한 긍정 기사를 놓친다.
    assert pn > pp
    assert decide_label(pp, pn) == "neutral"
    assert decide_label(pp, pn, neutral_threshold=0.30) == "negative"
    assert decide_label(*agg_topk_mean(pos, neg, topk=2)) == "positive"


def test_max_overcalls_mixed():
    """두 축의 최고값이 서로 다른 청크에서 와서 과하게 mixed가 된다."""
    pos = [0.91, 0.10]
    neg = [0.08, 0.88]
    assert decide_label(*agg_max(pos, neg)) == "mixed"
    assert decide_label(*agg_topk_mean(pos, neg, topk=1)) == "positive"


def test_weighted_mean_uses_lengths():
    pp, pn = agg_weighted_mean([1.0, 0.0], [0.0, 1.0], lengths=[300, 100])
    assert pp == pytest.approx(0.75) and pn == pytest.approx(0.25)


def test_aggregate_all_has_three_methods():
    out = aggregate_all([0.8, 0.2], [0.1, 0.3], [100, 100], topk=2)
    assert set(out) == {"weighted_mean", "max", "topk_mean"}
    assert all({"p_pos", "p_neg"} == set(v) for v in out.values())


def test_aggregate_rejects_unknown_method():
    with pytest.raises(ValueError):
        aggregate([0.5], [0.5], method="median")


def test_aggregate_rejects_axis_length_mismatch():
    """청크는 한 번만 쪼개서 두 축이 공유해야 한다."""
    with pytest.raises(ValueError):
        agg_topk_mean([0.5, 0.5], [0.5])


def test_aggregate_handles_empty():
    for m in ("weighted_mean", "max", "topk_mean"):
        assert aggregate([], [], method=m) == (0.0, 0.0)


def test_topk_larger_than_n_chunks():
    pp, pn = agg_topk_mean([0.6], [0.2], topk=5)
    assert (pp, pn) == (0.6, 0.2)


def test_topk_mean_is_deterministic_on_ties():
    pos, neg = [0.7, 0.7, 0.7], [0.2, 0.2, 0.2]
    assert agg_topk_mean(pos, neg, topk=2) == agg_topk_mean(pos, neg, topk=2)


# --- 진단값 -----------------------------------------------------------------
def test_neutral_baseline_detects_mild_asymmetry():
    d = neutral_baseline([0.15] * 8 + [0.88], [0.25] * 8 + [0.12], band=0.15)
    assert d["n"] == 8
    assert d["gap"] == pytest.approx(-0.10, abs=1e-6)   # 0이 아니면 편향 존재


def test_neutral_baseline_band_blindspot_covered_by_lowmax():
    """편향이 크면 그 청크가 band 밖으로 밀려난다. lowmax 기준이 이를 잡는다."""
    d = neutral_baseline([0.15] * 8 + [0.88], [0.45] * 8 + [0.12], band=0.15)
    assert d["n"] == 0 and d["gap"] is None            # 원래 정의의 맹점
    assert d["n_lowmax"] == 8
    assert d["gap_lowmax"] == pytest.approx(-0.30, abs=1e-6)


def test_neutral_baseline_no_neutral_chunks():
    d = neutral_baseline([0.9, 0.1], [0.05, 0.95], band=0.15)
    assert d["n"] == 0 and d["gap"] is None
    assert d["n_lowmax"] == 0


def test_hypothesis_disagreement():
    agree = np.array([[0.80, 0.81, 0.79]])
    disagree = np.array([[0.20, 0.55, 0.90]])
    assert hypothesis_disagreement(agree) < hypothesis_disagreement(disagree)
    assert hypothesis_disagreement(np.zeros((0, 3))) == 0.0


def test_make_sentiment_shape():
    s = make_sentiment(0.88, 0.10)
    assert set(s) == {"label", "score", "confidence", "p_pos", "p_neg"}
    assert s["label"] == "positive"
    assert s["confidence"] == pytest.approx(0.88)
