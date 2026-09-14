"""텍스트 처리 — 정제 · 문장 분리 · 청킹 · 절단.

라벨링(teacher)과 학습(student) 양쪽이 같은 함수를 쓴다.
같은 텍스트를 보게 만드는 것이 train/serve 일치의 출발점이다.
"""
from __future__ import annotations

import re

# ---------------------------------------------------------------------
# 상용구 — 논조와 무관한 부분. 토큰만 잡아먹고 신호를 흐린다.
# ---------------------------------------------------------------------
_BOILERPLATE = [
    # [데일리한국 정백현 기자] / （東京＝共同） 같은 머리표
    re.compile(
        r"^\s*[\[\(（【][^\]\)）】]{0,40}"
        r"(기자|특파원|뉴스|일보|신문|記者|通信|共同|時事)"
        r"[^\]\)）】]{0,20}[\]\)）】]\s*"
    ),
    # 이메일
    re.compile(r"[\w.\-+]+@[\w.\-]+\.[A-Za-z]{2,}"),
    # 저작권 문구 — 그 줄 끝까지
    re.compile(
        r"(저작권자|무단\s*전재|재배포\s*금지|All rights reserved|"
        r"Alle Rechte vorbehalten|無断転載|転載を禁じます)[^\n]*",
        re.I,
    ),
    # "관련기사" 이후는 다른 기사 제목 목록 — 전부 버림
    re.compile(
        r"\n\s*(관련\s*기사|関連記事|Read more|Mehr zum Thema|Lesen Sie auch|"
        r"あわせて読みたい)\b[\s\S]*$",
        re.I,
    ),
    # docomo 포털 제목 꼬리표
    re.compile(r"（[^）]{0,30}）\s*｜\s*ｄメニューニュース\s*$"),
]

# 문장 끝 — 서양 문장부호 뒤 공백, CJK 문장부호, 줄바꿈
_SENT_END = re.compile(r"(?<=[.!?])\s+|(?<=[。！？])|\n+")


def clean_text(s: str | None) -> str:
    s = s or ""
    for pat in _BOILERPLATE:
        s = pat.sub("", s)
    s = re.sub(r"[ \t]+", " ", s)          # 연속 공백 → 하나
    s = re.sub(r"\n{3,}", "\n\n", s)       # 빈 줄 3개 이상 → 2개
    return s.strip()


def build_text(title: str, body: str) -> str:
    """제목을 앞에 둔 학습·라벨링 입력. NLP worker 의 build_article_text 와 같은 형태."""
    title = (title or "").strip()
    body = (body or "").strip()
    return f"{title}\n\n{body}" if body else title


def split_sentences(text: str) -> list[str]:
    return [p.strip() for p in _SENT_END.split(text or "") if p and p.strip()]


def chunk_by_tokens(text: str, tokenizer, chunk_tokens: int) -> list[tuple[str, int]]:
    """문장 경계를 지키며 chunk_tokens 이하로 묶는다.

    반환: [(청크 텍스트, 토큰 수), ...]
    토큰 수는 집계 시 길이 가중치로 쓴다.

    문장 단위로 자르는 이유 — 토큰 수로 뚝 자르면 언어별로 담기는 내용이 달라진다.
    (한글은 영어보다 토큰이 많이 쪼개져서 같은 토큰 수에 더 적은 내용이 들어간다)
    """
    sents = split_sentences(text)
    if not sents:
        return []

    # 문장별 토큰 수 — 한 번에 인코딩해서 왕복을 줄인다
    lens = [len(ids) for ids in tokenizer(sents, add_special_tokens=False)["input_ids"]]

    chunks: list[tuple[str, int]] = []
    cur: list[str] = []
    cur_n = 0

    for sent, n in zip(sents, lens):
        # 문장 하나가 청크보다 길면 — 지금까지 것을 닫고, 그 문장은 잘라서 단독 청크로
        if n > chunk_tokens:
            if cur:
                chunks.append((" ".join(cur), cur_n))
                cur, cur_n = [], 0
            ids = tokenizer(sent, add_special_tokens=False)["input_ids"][:chunk_tokens]
            chunks.append((tokenizer.decode(ids), chunk_tokens))
            continue

        # 이 문장을 더하면 넘친다 — 지금까지 것을 닫는다
        if cur and cur_n + n > chunk_tokens:
            chunks.append((" ".join(cur), cur_n))
            cur, cur_n = [], 0

        cur.append(sent)
        cur_n += n

    if cur:
        chunks.append((" ".join(cur), cur_n))
    return chunks


def head_tail(ids: list[int], max_len: int, head: int, tail: int) -> list[int]:
    """max_len 초과 시 앞 head 개 + 뒤 tail 개만 남긴다.

    뉴스는 역피라미드 — 핵심은 앞, 기자의 마무리 논평은 뒤. 중간은 배경 설명이 많다.
    """
    if len(ids) <= max_len:
        return ids
    assert head + tail <= max_len, "head + tail 이 max_len 을 넘으면 안 된다"
    return ids[:head] + ids[-tail:]
