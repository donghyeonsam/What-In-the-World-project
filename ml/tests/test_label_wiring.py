"""label.py / split.py 배선 테스트. 가짜 teacher 를 끼워 HF 없이 돌린다.

검증 대상은 모델 품질이 아니라 배선이다.
- 게이트 탈락분도 버리지 않고 출력된다 (재개 산수의 전제: 입력 1행 = 출력 1행)
- 샤드 재개가 중복 처리 없이 이어진다
- alt_agg 3방식과 진단값이 남는다
- split 이 게이트 통과분만 층화 분할한다
"""
from __future__ import annotations

import json

import numpy as np
import pytest

from distill import label as label_mod
from distill import split as split_mod
from distill.config import load_config
from distill.hypotheses import CATEGORIES
from distill.io_utils import read_shards, write_jsonl
from distill.text import Chunk


class FakeTok:
    def encode(self, text, add_special_tokens=False):
        return list(range(len(text.split())))

    def decode(self, ids, skip_special_tokens=True):
        return " ".join("x" for _ in ids)


class FakeTeacher:
    """제목 안의 키워드로 분야·톤을 결정론적으로 만들어낸다."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.tok = FakeTok()

    def category_probs(self, lead, lang):
        p = np.full(len(CATEGORIES), 0.02)
        if "ECON" in lead:
            p[CATEGORIES.index("ECONOMY")] = 0.85
        elif "SPORT" in lead:
            p[CATEGORIES.index("SPORTS")] = 0.80
        else:                                   # 애매 → 분야 게이트 탈락
            p[:] = 1.0 / len(CATEGORIES)
        return p / p.sum()

    def tone_chunk_probs(self, chunks, category, lang):
        n = len(chunks)
        if any("GOOD" in c for c in chunks):
            pos = np.full((n, 3), 0.86) + np.linspace(-0.02, 0.02, 3)
            neg = np.full((n, 3), 0.11)
        elif any("MEH" in c for c in chunks):   # 톤 신뢰도 게이트 탈락
            pos, neg = np.full((n, 3), 0.30), np.full((n, 3), 0.28)
        else:
            pos, neg = np.full((n, 3), 0.12), np.full((n, 3), 0.83)
        return pos, neg


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    c = load_config()
    c["data"]["work_dir"] = str(tmp_path)
    c["teacher"]["shard_size"] = 4
    monkeypatch.setattr(label_mod, "Teacher", FakeTeacher)
    monkeypatch.setattr(label_mod, "chunk_by_tokens",
                        lambda text, tok, **kw: [Chunk(i, s, 50) for i, s in
                                                 enumerate(text.split("|"))])
    return c


def make_clean(cfg, n_each=6):
    rows = []
    kinds = [("ECON", "GOOD", "en"), ("ECON", "BAD", "ko"),
             ("SPORT", "GOOD", "ja"), ("SPORT", "BAD", "de"),
             ("ECON", "MEH", "en"), ("VAGUE", "GOOD", "de")]
    for k, (cat, tone, lang) in enumerate(kinds):
        for i in range(n_each):
            rows.append({
                "id": f"{cat}-{tone}-{i}", "url": f"https://e.com/{k}/{i}",
                "source": "src", "country": "X", "lang": lang,
                "title": f"{cat} headline {i}",
                "body": f"{tone} body one|neutral filler|{tone} body two",
            })
    write_jsonl(cfg["data"]["work_dir"] + "/clean.jsonl", rows)
    return rows


def test_label_keeps_gate_failures_and_shards(cfg):
    rows = make_clean(cfg)
    rep = label_mod.run(cfg)

    out = list(read_shards(cfg["data"]["work_dir"], "labeled"))
    assert len(out) == len(rows)                     # 입력 1행 = 출력 1행
    assert rep["processed"] == len(rows)

    reasons = rep["gate_reasons"]
    assert reasons.get("cat_margin", 0) + reasons.get("cat_p1", 0) == 6  # VAGUE
    assert reasons["tone_conf"] == 6                                  # MEH
    assert rep["gate_pass"] == 24

    passed = [r for r in out if r.get("gate_pass")]
    assert {r["category"] for r in passed} == {"ECONOMY", "SPORTS"}
    assert {r["sentiment"]["label"] for r in passed} == {"positive", "negative"}


def test_label_records_alt_agg_and_diagnostics(cfg):
    make_clean(cfg)
    label_mod.run(cfg)
    rec = next(r for r in read_shards(cfg["data"]["work_dir"], "labeled")
               if r.get("gate_pass"))
    assert set(rec["alt_agg"]) == {"weighted_mean", "max", "topk_mean"}
    assert rec["chunks"]["n"] == 3
    assert len(rec["chunks"]["p_pos"]) == len(rec["chunks"]["p_neg"])
    d = rec["diag"]
    assert d["hyp_disagreement_pos"] > 0             # 가설 3개가 조금씩 다름
    assert "neu_base" in d
    assert rec["sentiment"]["score"] == pytest.approx(
        50 * (1 + rec["sentiment"]["p_pos"] - rec["sentiment"]["p_neg"]), abs=1e-3)


def test_label_resumes_without_duplicates(cfg):
    make_clean(cfg)
    label_mod.run(cfg, limit=12)
    first = list(read_shards(cfg["data"]["work_dir"], "labeled"))
    assert len(first) == 12
    label_mod.run(cfg)                               # 재개
    allrows = list(read_shards(cfg["data"]["work_dir"], "labeled"))
    ids = [r["id"] for r in allrows]
    assert len(ids) == 36 and len(set(ids)) == 36


def test_label_report_written(cfg):
    make_clean(cfg)
    label_mod.run(cfg)
    rep = json.loads((__import__("pathlib").Path(cfg["data"]["work_dir"])
                      / "label_report.json").read_text(encoding="utf-8"))
    assert rep["aggregate"]["method"] == "topk_mean"
    assert "ECONOMY|en" in rep["crosstab"]


def test_split_uses_only_gate_passed(cfg):
    make_clean(cfg)
    label_mod.run(cfg)
    cfg["student"]["min_train_per_category"] = 1
    rep = split_mod.run(cfg)
    assert rep["gate_passed"] == 24
    assert rep["train"] + rep["val"] == 24
    assert set(rep["by_category"]) == {"ECONOMY", "SPORTS"}
    tr = list(__import__("distill.io_utils", fromlist=["read_jsonl"]).read_jsonl(
        __import__("pathlib").Path(cfg["data"]["work_dir"]) / "train.jsonl"))
    assert "chunks" not in tr[0]                     # 학습셋에서는 청크 배열 제거
    assert {"sentiment", "category", "lang", "title", "body"} <= set(tr[0])
