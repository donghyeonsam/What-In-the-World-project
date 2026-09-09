"""config.yaml 검증과 가설 구조 테스트. HF 불필요."""
from __future__ import annotations

import pytest

from distill.config import load_config
from distill.hypotheses import (CATEGORIES, flat_category_pairs,
                               flat_tone_hypotheses, tone_hypotheses)


@pytest.fixture(scope="module")
def cfg():
    return load_config()


def test_config_loads_and_validates(cfg):
    assert len(cfg.categories) == 6
    assert cfg.aggregate["method"] == "topk_mean"
    assert cfg.aggregate["topk"] == 2
    assert cfg.teacher["max_length"] == 512


def test_config_dot_access_and_require(cfg):
    assert cfg.gates.require("tone_min_conf") == 0.60
    with pytest.raises(KeyError):
        cfg.gates.require("tone_min_confidence")     # 오타는 조용히 넘기지 않는다
    with pytest.raises(AttributeError):
        _ = cfg.nonexistent_section


def test_serving_shared_constants_present(cfg):
    """서빙과 어긋나면 조용히 정확도만 떨어지는 값들."""
    assert cfg.category_clf["max_body_chars"] == 4000
    assert cfg.category_clf["mean_center"] is True
    assert cfg.teacher["hypothesis_lang"] in ("en", "ko")


def test_category_hypotheses_two_each():
    pairs = flat_category_pairs("en")
    assert len(pairs) == 12
    assert [c for c, _ in pairs[:2]] == ["POLITICS", "POLITICS"]


def test_tone_hypotheses_three_per_polarity():
    hyps, per_pol = flat_tone_hypotheses("SPORTS", "en")
    assert per_pol == 3 and len(hyps) == 6


def test_economy_tech_negative_drops_risk():
    for lang in ("en", "ko"):
        for cat in ("ECONOMY", "TECH"):
            joined = " ".join(tone_hypotheses(cat, lang)["neg"]).lower()
            assert "risk" not in joined and "리스크" not in joined


def test_all_categories_covered_in_both_langs():
    for lang in ("en", "ko"):
        for c in CATEGORIES:
            assert set(tone_hypotheses(c, lang)) == {"pos", "neg"}


def test_unknown_lang_and_category_raise():
    with pytest.raises(ValueError):
        tone_hypotheses("POLITICS", "fr")
    with pytest.raises(ValueError):
        tone_hypotheses("WEATHER", "en")
