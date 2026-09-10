"""[1] teacher 라벨링. 파이프라인에서 가장 무거운 단계 (GPU).

python -m distill.label --limit 500     # 검증용. 분야×언어 교차표 확보
python -m distill.label                 # 전체. 샤드 단위 재개됨

입력: work/clean.jsonl
출력: work/labeled.NNNNN.jsonl (샤드) + work/label_report.json

설계 요약
- 분야 (multi_label=False): 6개 분야가 서로 경쟁.
  분야 안에서 가설 2개의 entail 로짓 평균 → 분야 간 softmax → argmax.
- 톤 (multi_label=True): neutral을 버리고 entail vs contradiction 둘만 softmax.
  긍정·부정 가설이 경쟁하지 않아 '둘 다 높음'이 표현된다 → mixed 라벨 가능.
- NLI 라벨 인덱스는 반드시 config에서 찾는다. 하드코딩하면 0.980이
  0.020으로 조용히 뒤집힌다.
"""
from __future__ import annotations

import argparse
import json
import time
from collections import Counter, defaultdict

import numpy as np

from .config import load_config, work_path
from .hypotheses import CATEGORIES, flat_category_pairs, flat_tone_hypotheses
from .io_utils import (count_jsonl, read_jsonl, resume_state, shard_path,
                       write_jsonl)
from .scoring import (aggregate, aggregate_all, hypothesis_disagreement,
                      make_sentiment, neutral_baseline)
from .text import chunk_by_tokens

SHARD_STEM = "labeled"


class Teacher:
    """mDeBERTa NLI zero-shot 채점기."""

    def __init__(self, cfg):
        import torch
        from transformers import (AutoModelForSequenceClassification,
                                  AutoTokenizer)

        self.cfg = cfg
        self.torch = torch
        name = cfg.teacher["model"]
        dev = cfg.teacher.get("device", "cuda")
        self.device = dev if (dev != "cuda" or torch.cuda.is_available()) else "cpu"
        if self.device != dev:
            print(f"[teacher] {dev} 사용 불가 → {self.device}")

        self.tok = AutoTokenizer.from_pretrained(name)
        self.model = AutoModelForSequenceClassification.from_pretrained(name)
        self.model.to(self.device).eval()

        # --- NLI 라벨 인덱스 탐색 (하드코딩 금지) -------------------------
        id2label = {int(k): str(v).lower()
                    for k, v in self.model.config.id2label.items()}
        try:
            self.ent_idx = next(i for i, l in id2label.items() if "entail" in l)
            self.con_idx = next(i for i, l in id2label.items() if "contra" in l)
        except StopIteration:
            raise RuntimeError(
                f"NLI 라벨을 찾을 수 없음: {id2label}. NLI 모델이 맞는지 확인") from None
        print(f"[teacher] {name}\n  id2label={id2label} "
              f"ent={self.ent_idx} con={self.con_idx} device={self.device}")

        self.batch_size = int(cfg.teacher["batch_size"])
        self.max_length = int(cfg.teacher["max_length"])

    def _logits(self, premises: list[str], hypotheses: list[str]) -> np.ndarray:
        """(N, 3) NLI 로짓. truncation='only_first' — 가설은 자르지 않는다."""
        outs = []
        with self.torch.no_grad():
            for i in range(0, len(premises), self.batch_size):
                enc = self.tok(premises[i:i + self.batch_size],
                               hypotheses[i:i + self.batch_size],
                               return_tensors="pt", padding=True,
                               truncation="only_first",
                               max_length=self.max_length)
                enc = {k: v.to(self.device) for k, v in enc.items()}
                outs.append(self.model(**enc).logits.float().cpu().numpy())
        return np.concatenate(outs, axis=0) if outs else np.zeros((0, 3))

    # --- 분야: 분야 간 경쟁 (multi_label=False) --------------------------
    def category_probs(self, lead: str, lang: str) -> np.ndarray:
        pairs = flat_category_pairs(lang)
        logits = self._logits([lead] * len(pairs), [h for _, h in pairs])
        ent = logits[:, self.ent_idx].reshape(len(CATEGORIES), -1).mean(axis=1)
        e = np.exp(ent - ent.max())
        return e / e.sum()

    # --- 톤: 축끼리 경쟁 없음 (multi_label=True) -------------------------
    def tone_chunk_probs(self, chunks: list[str], category: str,
                         lang: str) -> tuple[np.ndarray, np.ndarray]:
        """(n_chunks, 3) 긍정 / (n_chunks, 3) 부정 — 가설별 p_entail."""
        hyps, per_pol = flat_tone_hypotheses(category, lang)
        premises, hypos = [], []
        for c in chunks:
            for h in hyps:
                premises.append(c)
                hypos.append(h)
        logits = self._logits(premises, hypos)
        two = logits[:, [self.con_idx, self.ent_idx]]
        m = two.max(axis=1, keepdims=True)
        e = np.exp(two - m)
        p_ent = (e[:, 1] / e.sum(axis=1)).reshape(len(chunks), len(hyps))
        return p_ent[:, :per_pol], p_ent[:, per_pol:]


def label_one(art: dict, teacher: Teacher, cfg) -> dict:
    """기사 1건 → 라벨 레코드. 게이트 탈락분도 버리지 않고 표시만 한다."""
    lang_h = cfg.teacher["hypothesis_lang"]
    text = f"{art['title']}\n\n{art['body']}"

    # 분야
    lead = text[:int(cfg.teacher["lead_chars"])]
    cp = teacher.category_probs(lead, lang_h)
    order = np.argsort(-cp)
    cat = CATEGORIES[int(order[0])]
    p1, p2 = float(cp[order[0]]), float(cp[order[1]])
    margin = p1 - p2

    rec = {
        "id": art["id"], "url": art["url"], "source": art["source"],
        "country": art["country"], "lang": art["lang"],
        "title": art["title"], "body": art["body"],
        "category": cat,
        "category_probs": {c: round(float(cp[i]), 6) for i, c in enumerate(CATEGORIES)},
        "cat_p1": round(p1, 6), "cat_margin": round(margin, 6),
    }

    g = cfg.gates
    if p1 < float(g["category_min_p1"]):
        rec.update(gate_pass=False, gate_reason="cat_p1")
        return rec
    if margin < float(g["category_min_margin"]):
        rec.update(gate_pass=False, gate_reason="cat_margin")
        return rec

    # 톤. 청크는 한 번만 쪼개서 긍정·부정이 공유한다.
    chunks = chunk_by_tokens(text, teacher.tok,
                             max_tokens=int(cfg.teacher["chunk_tokens"]),
                             min_tokens=int(cfg.teacher["min_chunk_tokens"]),
                             max_chunks=int(cfg.teacher.get("max_chunks", 24)))
    if not chunks:
        rec.update(gate_pass=False, gate_reason="no_chunk")
        return rec

    pos_h, neg_h = teacher.tone_chunk_probs([c.text for c in chunks], cat, lang_h)
    p_pos_c, p_neg_c = pos_h.mean(axis=1), neg_h.mean(axis=1)
    lengths = [c.n_tokens for c in chunks]

    agg = cfg.aggregate
    p_pos, p_neg = aggregate(p_pos_c, p_neg_c, lengths,
                             method=agg["method"], topk=int(agg["topk"]))
    sent = make_sentiment(p_pos, p_neg,
                          float(cfg.labels["mixed_threshold"]),
                          float(cfg.labels["neutral_threshold"]))

    rec["sentiment"] = sent
    rec["alt_agg"] = aggregate_all(p_pos_c, p_neg_c, lengths, topk=int(agg["topk"]))
    rec["chunks"] = {
        "n": len(chunks),
        "tokens": lengths,
        "p_pos": [round(float(x), 6) for x in p_pos_c],
        "p_neg": [round(float(x), 6) for x in p_neg_c],
    }
    rec["diag"] = {
        "hyp_disagreement_pos": round(hypothesis_disagreement(pos_h), 6),
        "hyp_disagreement_neg": round(hypothesis_disagreement(neg_h), 6),
        "neu_base": neutral_baseline(p_pos_c, p_neg_c,
                                     band=float(agg.get("neutral_band", 0.15))),
    }

    if sent["confidence"] < float(g["tone_min_conf"]):
        rec.update(gate_pass=False, gate_reason="tone_conf")
        return rec
    rec.update(gate_pass=True, gate_reason=None)
    return rec


def print_crosstab(counts: dict, langs: list[str]) -> None:
    """분야 × 언어 교차표. 필요 수집 일수를 확정하는 근거."""
    print("\n[분야 × 언어 교차표] (게이트 통과분)")
    head = f"  {'':<9}" + "".join(f"{l:>8}" for l in langs) + f"{'TOTAL':>9}"
    print(head)
    col = {l: 0 for l in langs}
    for c in CATEGORIES:
        row = [counts.get((c, l), 0) for l in langs]
        for l, v in zip(langs, row):
            col[l] += v
        print(f"  {c:<9}" + "".join(f"{v:>8,}" for v in row) + f"{sum(row):>9,}")
    print(f"  {'TOTAL':<9}" + "".join(f"{col[l]:>8,}" for l in langs) +
          f"{sum(col.values()):>9,}")
    smallest = min(((c, l, counts.get((c, l), 0))
                    for c in CATEGORIES for l in langs), key=lambda t: t[2])
    print(f"  최소 칸: {smallest[0]}/{smallest[1]} = {smallest[2]:,}건 "
          "← 이 칸이 전체 일정을 결정한다")


def run(cfg, limit: int | None = None, restart: bool = False) -> dict:
    src = work_path(cfg, "clean.jsonl")
    if not src.exists():
        raise FileNotFoundError(f"{src} 없음. 먼저 python -m distill.prepare 실행")

    wd = work_path(cfg, ".keep").parent
    next_shard, done = (0, 0) if restart else resume_state(wd, SHARD_STEM)
    if done:
        print(f"[label] 재개: 샤드 {next_shard}개 / {done:,}건 처리됨")

    teacher = Teacher(cfg)
    shard_size = int(cfg.teacher["shard_size"])
    langs = sorted(set(cfg.data["country_to_lang"].values()))

    buf: list[dict] = []
    n = 0
    gates: Counter = Counter()
    labels: Counter = Counter()
    cross: dict = defaultdict(int)
    disagree: list[float] = []
    neu_gap: list[float] = []
    t0 = time.time()

    def flush() -> None:
        nonlocal buf, next_shard
        if not buf:
            return
        p = shard_path(wd, SHARD_STEM, next_shard)
        write_jsonl(p, buf)
        print(f"  → {p.name} ({len(buf):,}건, {time.time()-t0:.0f}s 경과)")
        next_shard += 1
        buf = []

    for art in read_jsonl(src, limit=limit, skip=done):
        rec = label_one(art, teacher, cfg)
        buf.append(rec)
        n += 1
        gates[rec.get("gate_reason") or "pass"] += 1
        if rec.get("gate_pass"):
            labels[rec["sentiment"]["label"]] += 1
            cross[(rec["category"], rec["lang"])] += 1
        if "diag" in rec:
            d = rec["diag"]
            disagree.append(max(d["hyp_disagreement_pos"], d["hyp_disagreement_neg"]))
            g = d["neu_base"]["gap_lowmax"]
            if g is None:
                g = d["neu_base"]["gap"]
            if g is not None:
                neu_gap.append(g)
        if len(buf) >= shard_size:
            flush()
    flush()

    passed = gates.get("pass", 0)
    report = {
        "processed": n,
        "gate_pass": passed,
        "gate_pass_ratio": round(passed / n, 4) if n else 0.0,
        "gate_reasons": dict(gates.most_common()),
        "label_dist": dict(labels.most_common()),
        "crosstab": {f"{c}|{l}": v for (c, l), v in sorted(cross.items())},
        "diag": {
            "hyp_disagreement_mean": round(float(np.mean(disagree)), 6) if disagree else None,
            "hyp_disagreement_p95": round(float(np.percentile(disagree, 95)), 6) if disagree else None,
            "neu_base_gap_mean": round(float(np.mean(neu_gap)), 6) if neu_gap else None,
        },
        "elapsed_sec": round(time.time() - t0, 1),
        "aggregate": dict(cfg.aggregate),
        "gates": dict(cfg.gates),
        "hypothesis_lang": cfg.teacher["hypothesis_lang"],
    }
    work_path(cfg, "label_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n[label] {n:,}건 처리 / 게이트 통과 {passed:,} "
          f"({report['gate_pass_ratio']:.1%})")
    for k, v in report["gate_reasons"].items():
        print(f"  {k:14s} {v:>7,}")
    print(f"  라벨 분포: {report['label_dist']}")
    d = report["diag"]
    print(f"  hyp_disagreement 평균 {d['hyp_disagreement_mean']} / p95 {d['hyp_disagreement_p95']}")
    print(f"  neu_base gap 평균 {d['neu_base_gap_mean']} "
          "(0에서 멀면 축 기저율 비대칭 → weighted_mean 사용 금지 근거)")
    print_crosstab(cross, langs)
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="[1] teacher 라벨링")
    ap.add_argument("--config", default=None)
    ap.add_argument("--limit", type=int, default=None, help="검증용 상한 (예: 500)")
    ap.add_argument("--restart", action="store_true", help="기존 샤드 무시하고 처음부터")
    a = ap.parse_args()
    run(load_config(a.config), limit=a.limit, restart=a.restart)


if __name__ == "__main__":
    main()
