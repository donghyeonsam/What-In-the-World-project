"""정제 / 청킹 / head-tail 절단.

주의: clean_text 규칙은 NLP worker와 동일해야 한다.
여기만 고치면 학습과 서빙의 입력 분포가 조용히 어긋난다.

이 모듈은 transformers를 import하지 않는다. tokenizer를 인자로 받으므로
HF가 막힌 환경에서도 가짜 토크나이저로 테스트가 돌아간다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# --- 상용구 5종 -------------------------------------------------------------
BOILERPLATE: list[tuple[str, re.Pattern]] = [
    ("copyright", re.compile(
        r"[^\n]*(?:무단\s*전재|재배포\s*금지|저작권자\s*\(?c\)?|"
        r"copyright\s*(?:\u00a9|\(c\))?\s*\d{0,4}|all rights reserved|"
        r"alle rechte vorbehalten|無断転載|転載を禁)[^\n]*", re.I)),
    ("byline", re.compile(
        r"^\s*(?:[가-힣]{2,4}\s*(?:기자|특파원|통신원)|"
        r"[Bb][Yy]\s+[A-Z][\w'\u2019-]+(?:\s+[A-Z][\w'\u2019-]+){0,3}|"
        r"[Vv]on\s+[A-Z][\wäöüß-]+(?:\s+[A-Z][\wäöüß-]+)?)"
        r"\s*(?:[<(\[][^>)\]]*[>)\]])?\s*$", re.M)),
    ("credit", re.compile(
        r"[^\n]*(?:\[?사진\s*[=·]|사진\s*제공|photo(?:graph)?\s*:|"
        r"image\s*:|foto\s*:|写真\s*[=・])[^\n]*", re.I)),
    ("promo", re.compile(
        r"[^\n]*(?:구독\s*하기|뉴스레터|기사\s*제보|관련\s*기사|더\s*보기|"
        r"sign up (?:for|to) our|subscribe to our|follow us on|read more:|"
        r"mehr dazu:|weiterlesen|関連記事|この記事の続き)[^\n]*", re.I)),
    ("consent", re.compile(
        r"[^\n]*(?:wie gewohnt mit werbung|adblocker|cookies? (?:zu|akzeptieren|"
        r"settings|policy)|datenschutzerkl|need assistance\?|enable javascript|"
        r"javascript を有効|willkommen auf golem)[^\n]*", re.I)),
]

_WS = re.compile(r"[ \t\u3000]+")
_BLANK = re.compile(r"\n{3,}")
_SENT = re.compile(
    r"[^\n]*?(?:[。．！？]+|[!?]+|(?<![A-Z])\.(?=\s|$)|$)")
_WORD = re.compile(r"[\w가-힣ぁ-んァ-ヶ一-龥]{2,}", re.U)


def boilerplate_hits(text: str) -> list[str]:
    """진단용. 어떤 규칙이 걸렸는지 이름만 돌려준다."""
    return [name for name, pat in BOILERPLATE if pat.search(text or "")]


def clean_text(text: str | None, *, drop_boilerplate: bool = True) -> str:
    if not text:
        return ""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\u200b", "").replace("\xa0", " ")
    if drop_boilerplate:
        for _, pat in BOILERPLATE:
            t = pat.sub("\n", t)
    lines = (_WS.sub(" ", ln).strip() for ln in t.split("\n"))
    t = "\n".join(lines)
    return _BLANK.sub("\n\n", t).strip()


def longest_line(text: str) -> int:
    """포털 헤드라인 목록 탐지용. 가장 긴 줄이 짧으면 기사 본문이 아니다."""
    return max((len(ln.strip()) for ln in (text or "").split("\n")), default=0)


def title_term_overlap(title: str, body: str) -> float:
    """제목 핵심어가 본문에 등장하는 비율. excite류 판별 진단값 (정상 ~0.62)."""
    terms = {w.lower() for w in _WORD.findall(title or "")}
    if not terms:
        return 0.0
    low = (body or "").lower()
    return sum(1 for t in terms if t in low) / len(terms)


def split_sentences(text: str) -> list[str]:
    """줄 단위로 먼저 끊고 그 안에서 문장 분리. 4개 언어 종결부호를 함께 본다."""
    out: list[str] = []
    for line in (text or "").split("\n"):
        line = line.strip()
        if not line:
            continue
        for m in _SENT.finditer(line):
            s = m.group(0).strip()
            if s:
                out.append(s)
    return out


@dataclass
class Chunk:
    index: int
    text: str
    n_tokens: int


def n_tokens(tokenizer, text: str) -> int:
    return len(tokenizer.encode(text, add_special_tokens=False))


def _hard_split(tokenizer, sentence: str, max_tokens: int) -> list[str]:
    """한 문장이 예산을 넘을 때만 쓰는 최후 수단."""
    ids = tokenizer.encode(sentence, add_special_tokens=False)
    return [tokenizer.decode(ids[i:i + max_tokens], skip_special_tokens=True)
            for i in range(0, len(ids), max_tokens)]


def chunk_by_tokens(text: str, tokenizer, max_tokens: int = 200,
                    min_tokens: int = 20, max_chunks: int | None = None) -> list[Chunk]:
    """문장 경계를 지키면서 max_tokens 이하로 묶는다.

    이 결과를 긍정·부정 가설이 그대로 공유한다. 축마다 다시 쪼개면
    청크 수가 달라져서 "topk_mean이 두 축에서 같은 청크를 고른다"는
    보장이 깨진다.

    꼬리 흡수(min_tokens)가 없으면 3토큰짜리 조각이 생기고,
    극성차가 짧은 조각에서 튀기 때문에 topk_mean이 그걸 상위로 뽑는다.
    """
    pieces: list[str] = []
    buf: list[str] = []
    buf_n = 0
    for sent in split_sentences(text):
        k = n_tokens(tokenizer, sent)
        if k > max_tokens:
            if buf:
                pieces.append(" ".join(buf))
                buf, buf_n = [], 0
            pieces.extend(_hard_split(tokenizer, sent, max_tokens))
            continue
        if buf_n + k > max_tokens and buf:
            pieces.append(" ".join(buf))
            buf, buf_n = [], 0
        buf.append(sent)
        buf_n += k
    if buf:
        pieces.append(" ".join(buf))

    chunks = [Chunk(i, p, n_tokens(tokenizer, p)) for i, p in enumerate(pieces)]
    if len(chunks) >= 2 and chunks[-1].n_tokens < min_tokens:
        merged = chunks[-2].text + " " + chunks[-1].text
        chunks[-2] = Chunk(chunks[-2].index, merged, n_tokens(tokenizer, merged))
        chunks.pop()
    if max_chunks is not None:
        chunks = chunks[:max_chunks]
    return chunks


def head_tail_ids(ids: list[int], max_length: int,
                  head_tokens: int, tail_tokens: int) -> list[int]:
    """기사는 앞과 끝에 결론이 몰린다. 중간을 버린다.

    특수토큰이 없는 상태의 id 리스트를 받는다.
    (특수토큰 제거 → 자르기 → 재부착 순서를 지켜야 함)
    """
    if len(ids) <= max_length:
        return list(ids)
    if head_tokens + tail_tokens > max_length:
        raise ValueError(
            f"head+tail({head_tokens}+{tail_tokens}) > max_length({max_length})")
    return list(ids[:head_tokens]) + list(ids[-tail_tokens:])
