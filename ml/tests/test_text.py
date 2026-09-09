"""text.py 단독 테스트. HF 없이 돌아가야 한다 (컨테이너 프록시 403)."""
from __future__ import annotations

import pytest

from distill.text import (boilerplate_hits, chunk_by_tokens, clean_text,
                          head_tail_ids, longest_line, split_sentences,
                          title_term_overlap)


class FakeTokenizer:
    """공백 단위 토크나이저. 청킹 로직만 검증한다 (실제 서브워드 수와 무관)."""

    def __init__(self) -> None:
        self.vocab: dict[str, int] = {}
        self.inv: dict[int, str] = {}

    def _id(self, tok: str) -> int:
        if tok not in self.vocab:
            i = len(self.vocab) + 5
            self.vocab[tok] = i
            self.inv[i] = tok
        return self.vocab[tok]

    def encode(self, text: str, add_special_tokens: bool = False) -> list[int]:
        return [self._id(t) for t in text.split()]

    def decode(self, ids: list[int], skip_special_tokens: bool = True) -> str:
        return " ".join(self.inv.get(i, "") for i in ids).strip()


@pytest.fixture
def tok() -> FakeTokenizer:
    return FakeTokenizer()


def words(n: int, w: str = "가") -> str:
    return " ".join([w] * n)


# --- clean_text -------------------------------------------------------------
@pytest.mark.parametrize("name,text", [
    ("copyright", "본문입니다.\n무단전재 및 재배포 금지"),
    ("copyright", "Body text.\nCopyright 2026 Reuters. All rights reserved."),
    ("byline", "홍길동 기자\n본문입니다."),
    ("byline", "By Jane Smith\nBody text."),
    ("credit", "본문입니다.\n[사진=연합뉴스]"),
    ("promo", "본문입니다.\n관련 기사 더 보기"),
    ("consent", "Willkommen auf Golem.de!\nBitte Adblocker deaktivieren."),
])
def test_boilerplate_detected(name, text):
    assert name in boilerplate_hits(text)


def test_boilerplate_removed():
    cleaned = clean_text("본문입니다.\n[사진=연합뉴스]\n무단전재 및 재배포 금지")
    assert cleaned == "본문입니다."


def test_clean_text_keeps_body():
    assert clean_text("정부는 오늘 대책을 발표했다.\n\n김철수 기자") == \
        "정부는 오늘 대책을 발표했다."


def test_clean_text_normalizes_whitespace():
    src = "  a\u3000\u3000b  \r\n\n\n\nc\xa0d  "
    assert clean_text(src) == "a b\n\nc d"


def test_clean_text_handles_none():
    assert clean_text(None) == "" and clean_text("") == ""


def test_longest_line_detects_headline_list():
    assert longest_line("속보 A\n속보 B\n단독 C") < 40
    assert longest_line("정부는 오늘 종합 대책을 발표하고 후속 조치를 예고했다고 관계 부처가 밝혔다.") >= 40


def test_title_term_overlap():
    title = "반도체 수출 증가"
    assert title_term_overlap(title, "반도체 수출이 증가했다고 밝혔다.") == 1.0
    assert title_term_overlap(title, "스포츠 경기 결과입니다.") == 0.0
    assert title_term_overlap("", "본문") == 0.0


# --- split_sentences --------------------------------------------------------
def test_split_sentences_multilingual():
    src = "첫 문장이다. 두 번째다!\n日本語の文です。次の文です。\nA sentence. Another one?"
    sents = split_sentences(src)
    assert len(sents) == 6
    assert sents[2].endswith("。")


def test_split_sentences_keeps_abbrev_and_decimal():
    """U.S. / 3.5 에서 잘리면 청크 경계가 무의미하게 잘게 쪼개진다."""
    sents = split_sentences("The U.S. economy grew 3.5 percent last year. It slowed.")
    assert len(sents) == 2


# --- chunk_by_tokens --------------------------------------------------------
def test_chunk_respects_budget(tok):
    text = " ".join(f"{words(30)} 문장{i}." for i in range(10))
    chunks = chunk_by_tokens(text, tok, max_tokens=200)
    assert all(c.n_tokens <= 200 for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))


def test_chunk_respects_sentence_boundary(tok):
    text = f"{words(120)} 끝. {words(120)} 끝."
    assert len(chunk_by_tokens(text, tok, max_tokens=200)) == 2


def test_chunk_hard_splits_long_sentence(tok):
    chunks = chunk_by_tokens(words(450) + " 끝.", tok, max_tokens=200)
    assert len(chunks) == 3 and all(c.n_tokens <= 200 for c in chunks)


def test_chunk_merges_tiny_tail(tok):
    chunks = chunk_by_tokens(f"{words(150)} 끝. 짧다.", tok,
                             max_tokens=200, min_tokens=20)
    assert len(chunks) == 1 and "짧다" in chunks[0].text


def test_chunk_respects_max_chunks(tok):
    text = " ".join(f"{words(190)} 끝{i}." for i in range(10))
    assert len(chunk_by_tokens(text, tok, max_tokens=200, max_chunks=4)) == 4


def test_chunk_is_deterministic(tok):
    """긍정·부정 가설이 같은 청크를 공유해야 topk_mean이 성립한다."""
    text = " ".join(f"{words(40)} 문장{i}." for i in range(6))
    a = chunk_by_tokens(text, tok, max_tokens=200)
    b = chunk_by_tokens(text, tok, max_tokens=200)
    assert [(c.index, c.text, c.n_tokens) for c in a] == \
           [(c.index, c.text, c.n_tokens) for c in b]


def test_chunk_empty(tok):
    assert chunk_by_tokens("", tok) == []


# --- head_tail --------------------------------------------------------------
def test_head_tail_passthrough_when_short():
    ids = list(range(100))
    assert head_tail_ids(ids, 4096, 3072, 1024) == ids


def test_head_tail_keeps_both_ends():
    out = head_tail_ids(list(range(10000)), 4096, 3072, 1024)
    assert len(out) == 4096
    assert out[0] == 0 and out[-1] == 9999
    assert out[3071] == 3071 and out[3072] == 10000 - 1024


def test_head_tail_rejects_bad_budget():
    with pytest.raises(ValueError):
        head_tail_ids(list(range(10000)), 512, 3072, 1024)
