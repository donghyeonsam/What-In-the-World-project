"""CPU 단위 테스트 — 모델 없이 정제·청킹·집계·라벨 로직을 검증한다.

    pytest tests/ -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from distill.scoring import aggregate, decide_label, tone_point  # noqa: E402
from distill.text import build_text, chunk_by_tokens, clean_text, head_tail, split_sentences  # noqa: E402


# ---------------------------------------------------------------- 정제
def test_clean_removes_reporter_prefix():
    assert clean_text("[데일리한국 정백현 기자] 본문 시작") == "본문 시작"


def test_clean_removes_email_and_copyright():
    s = "본문. 문의 abc@news.com 저작권자 ⓒ 뉴스 무단전재 금지"
    out = clean_text(s)
    assert "@" not in out and "저작권" not in out


def test_clean_cuts_related_articles():
    s = "본문 첫 문장.\n\n관련기사\n다른 기사 제목 1\n다른 기사 제목 2"
    assert clean_text(s) == "본문 첫 문장."


def test_clean_docomo_title_tail():
    assert clean_text("제목입니다（東スポWEB）｜ｄメニューニュース") == "제목입니다"


def test_build_text_title_first():
    assert build_text("제목", "본문").startswith("제목\n\n")
    assert build_text("제목", "") == "제목"


# ---------------------------------------------------------------- 문장 분리
def test_split_sentences_multilingual():
    s = "첫 문장이다. 둘째 문장이다! Third one here? 日本語の文。次の文。"
    parts = split_sentences(s)
    assert len(parts) == 5


# ---------------------------------------------------------------- 청킹 (가짜 토크나이저)
class FakeTok:
    """공백 단위로 토큰을 세는 대체 토크나이저.

    HF 토크나이저와 같은 규약 — 문자열 하나면 평탄 리스트, 리스트면 리스트의 리스트.
    """
    def __call__(self, texts, add_special_tokens=False, truncation=False):
        if isinstance(texts, str):
            return {"input_ids": texts.split()}
        return {"input_ids": [t.split() for t in texts]}
    def decode(self, ids):
        return " ".join(ids)


def test_chunk_respects_limit_and_keeps_lengths():
    text = " ".join(f"w{i} w{i} w{i}." for i in range(20))   # 20문장 × 3토큰
    chunks = chunk_by_tokens(text, FakeTok(), chunk_tokens=7)
    assert all(n <= 7 for _, n in chunks)
    assert sum(n for _, n in chunks) == 60
    assert len(chunks) == 10                                # 7 안에 문장 2개(6토큰)씩


def test_chunk_oversized_sentence_is_truncated_alone():
    text = "a b c d e f g h i j. short one."
    chunks = chunk_by_tokens(text, FakeTok(), chunk_tokens=4)
    assert chunks[0][1] == 4 and chunks[0][0] == "a b c d"
    assert chunks[1][1] == 2


# ---------------------------------------------------------------- 절단
def test_head_tail_untouched_when_short():
    ids = list(range(10))
    assert head_tail(ids, 20, 15, 5) == ids


def test_head_tail_keeps_both_ends():
    ids = list(range(100))
    out = head_tail(ids, 20, 15, 5)
    assert out == list(range(15)) + list(range(95, 100))


# ---------------------------------------------------------------- 집계
def test_aggregate_weighted_mean():
    probs = np.array([[0.9, 0.1], [0.1, 0.9]])
    lens = np.array([3, 1])
    p, n = aggregate(probs, lens, "weighted_mean")
    assert abs(p - 0.7) < 1e-6 and abs(n - 0.3) < 1e-6


def test_aggregate_max_and_topk():
    probs = np.array([[0.2, 0.2], [0.9, 0.1], [0.1, 0.8]])
    lens = np.array([1, 1, 1])
    assert aggregate(probs, lens, "max") == (0.9, 0.8)
    p, n = aggregate(probs, lens, "topk_mean", topk=2)     # 극성 뚜렷한 2개: [0.9,0.1],[0.1,0.8]
    assert abs(p - 0.5) < 1e-6 and abs(n - 0.45) < 1e-6


# ---------------------------------------------------------------- 라벨
@pytest.mark.parametrize("pp,pn,exp", [
    (0.90, 0.05, "positive"),
    (0.10, 0.85, "negative"),
    (0.71, 0.68, "mixed"),
    (0.12, 0.09, "neutral"),
])
def test_decide_label(pp, pn, exp):
    assert decide_label(pp, pn, 0.5, 0.4) == exp


def test_mixed_and_neutral_share_score_but_not_label():
    assert tone_point(0.71, 0.68) == tone_point(0.12, 0.09)
    assert decide_label(0.71, 0.68, 0.5, 0.4) != decide_label(0.12, 0.09, 0.5, 0.4)
