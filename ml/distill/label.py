"""[stage 1] teacher 톤 라벨링 — work/clean.field.jsonl → work/labels/shard_XXXX.jsonl

분야는 이미 assign_field 가 붙였다(worker 분류기와 동일). teacher 는 톤만 맡는다.

기사 한 건에 대해
  ① 청킹 — 본문을 200토큰 청크로 쪼갠다 (teacher 상한 512 우회)
  ② 채점 — 청크마다 그 분야의 긍정 가설 3개, 부정 가설 3개를 독립 채점
            entail vs contradiction 둘만 softmax (multi_label=True 방식)
  ③ 앙상블 — 극성 내 평균 → 청크별 (P긍정, P부정)
  ④ 집계 — config.aggregate.method 로 기사 단위 확률로.
            나머지 두 방식도 alt_agg 에 남긴다 (나중에 비교 가능)
  ⑤ 게이트 — max(P긍정, P부정) 이 기준 미만이면 학습 제외 표시

부수적으로 진단값 두 개를 남긴다.
  hyp_disagreement — 앙상블 가설끼리 얼마나 어긋났나
  neu_base         — 중립 청크에서 두 축의 기저값 (축 비대칭 탐지용)

shard_size 건마다 파일로 저장한다. 중단돼도 같은 명령을 다시 실행하면
이미 있는 샤드는 건너뛰고 이어서 돈다.

실행
    python -m distill.label
    python -m distill.label --limit 500      # 검증용 소규모
"""
from __future__ import annotations

import argparse
import collections
import time

import numpy as np
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

from . import hypotheses
from .config import load_config, work_path
from .io_utils import iter_shards, read_jsonl, shard_path, write_jsonl
from .scoring import aggregate, decide_label, tone_point
from .text import build_text, chunk_by_tokens


class Teacher:
    def __init__(self, cfg) -> None:
        t = cfg.teacher
        self.cfg = cfg
        self.device = t.device if torch.cuda.is_available() else "cpu"
        self.batch_size = t.batch_size
        self.max_length = t.max_length

        self.tok = AutoTokenizer.from_pretrained(t.model)
        self.model = (
            AutoModelForSequenceClassification.from_pretrained(t.model)
            .to(self.device)
            .eval()
        )

        # NLI 라벨 인덱스 — 모델마다 순서가 다르다. 하드코딩하면 조용히 뒤집힌다.
        id2label = {int(k): v.lower() for k, v in self.model.config.id2label.items()}
        self.ent_idx = next(i for i, l in id2label.items() if "entail" in l)
        self.con_idx = next(i for i, l in id2label.items() if "contra" in l)
        print(f"teacher 라벨: {id2label} → entail={self.ent_idx}, contra={self.con_idx}")
        print(f"device={self.device}, batch_size={self.batch_size}")

        lang = t.hypothesis_lang
        self.fields = sorted(set(cfg_fields(cfg).values()))
        hypotheses.check(self.fields, lang)
        self.tone_hyps = {f: hypotheses.tone_hypotheses(lang, f) for f in self.fields}

    # ------------------------------------------------------------------
    @torch.no_grad()
    def _nli_logits(self, premises: list[str], hyps: list[str]) -> torch.Tensor:
        """(premise, hypothesis) 쌍 N개 → logits (N, 3). 배치로 나눠 돈다."""
        out = []
        for i in range(0, len(premises), self.batch_size):
            enc = self.tok(
                premises[i:i + self.batch_size],
                hyps[i:i + self.batch_size],
                truncation="only_first",      # 가설은 자르지 않고 premise 만 자른다
                max_length=self.max_length,
                padding=True,
                return_tensors="pt",
            ).to(self.device)
            with torch.autocast(self.device, dtype=torch.bfloat16,
                                enabled=self.device == "cuda"):
                logits = self.model(**enc).logits
            out.append(logits.float().cpu())
        return torch.cat(out, dim=0) if out else torch.zeros((0, 3))

    # ------------------------------------------------------------------
    def label_tone(self, rows: list[dict]) -> list[dict]:
        """청크별로 (긍정, 부정) 가설을 독립 채점하고 기사 단위로 집계."""
        chunk_tokens = self.cfg.teacher.chunk_tokens

        premises, hyps = [], []
        index = []          # (기사 idx, 청크 idx, 0=긍정/1=부정, 청크 토큰 수)
        n_chunks = []

        for i, r in enumerate(rows):
            text = build_text(r["title"], r["body"])
            chunks = chunk_by_tokens(text, self.tok, chunk_tokens)   # 한 번만 쪼갠다
            n_chunks.append(len(chunks))
            pos_hs, neg_hs = self.tone_hyps[r["field"]]
            for j, (ctext, clen) in enumerate(chunks):
                for h in pos_hs:
                    premises.append(ctext); hyps.append(h); index.append((i, j, 0, clen))
                for h in neg_hs:
                    premises.append(ctext); hyps.append(h); index.append((i, j, 1, clen))

        logits = self._nli_logits(premises, hyps)

        # multi_label=True 방식 — entail vs contradiction 두 개만 softmax.
        # 긍정·부정 가설이 서로 경쟁하지 않아 "둘 다 높음" 이 표현 가능하다.
        two = logits[:, [self.con_idx, self.ent_idx]]
        p_ent = torch.softmax(two, dim=-1)[:, 1].numpy()

        def _slot():
            return {"pos": [], "neg": [], "len": 0}
        per_article: list[dict[int, dict]] = [collections.defaultdict(_slot) for _ in rows]
        for (i, j, which, clen), p in zip(index, p_ent):
            slot = per_article[i][j]
            slot["pos" if which == 0 else "neg"].append(float(p))
            slot["len"] = clen

        agg_cfg = self.cfg.aggregate
        lab = self.cfg.labels
        g = self.cfg.gates
        results = []
        for i in range(len(rows)):
            chunks = per_article[i]
            if not chunks:
                results.append({"tone_pass": False, "n_chunks": 0})
                continue
            order = sorted(chunks)
            # 가설 앙상블 평균 → 청크별 (P긍정, P부정)
            probs = np.array([[np.mean(chunks[j]["pos"]), np.mean(chunks[j]["neg"])]
                              for j in order])
            lens = np.array([chunks[j]["len"] for j in order])

            # 가설 간 불일치 — 3개가 크게 어긋나면 그 기사는 애매하다는 신호
            hyp_std = float(np.mean(
                [np.std(chunks[j]["pos"]) for j in order] +
                [np.std(chunks[j]["neg"]) for j in order]))

            # 중립 청크 기저값 — 두 축이 편향 없다면 같아야 한다.
            # 다르면 가설 기저율이 비대칭이고, weighted_mean 이 그 편향을
            # 중립 청크 수만큼 누적한다.
            strength = np.abs(probs[:, 0] - probs[:, 1])
            neu = probs[strength < 0.15]
            neu_base = [round(float(neu[:, 0].mean()), 4),
                        round(float(neu[:, 1].mean()), 4)] if len(neu) else None

            p_pos, p_neg = aggregate(probs, lens, agg_cfg.method, agg_cfg.topk)
            alt = {m: aggregate(probs, lens, m, agg_cfg.topk)
                   for m in ("weighted_mean", "max", "topk_mean") if m != agg_cfg.method}

            results.append({
                "p_pos": round(p_pos, 4),
                "p_neg": round(p_neg, 4),
                "tone_label": decide_label(p_pos, p_neg,
                                           lab.mixed_threshold, lab.neutral_threshold),
                "tone_point": tone_point(p_pos, p_neg),
                "tone_conf": round(max(p_pos, p_neg), 4),
                "tone_pass": max(p_pos, p_neg) >= g.tone_min_conf,
                "hyp_disagreement": round(hyp_std, 4),
                "neu_base": neu_base,
                "n_chunks": n_chunks[i],
                "alt_agg": {m: [round(a, 4), round(b, 4)] for m, (a, b) in alt.items()},
            })
        return results


def cfg_fields(cfg) -> dict[int, str]:
    """config.fields 를 {field_id: 이름} 으로."""
    f = cfg.fields
    if isinstance(f, dict):
        return {int(k): v for k, v in f.items()}
    return dict(enumerate(f, 1))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="앞에서 N건만 (검증용)")
    args = ap.parse_args()

    cfg = load_config()
    labels_dir = cfg.data.work_dir / "labels"
    labels_dir.mkdir(parents=True, exist_ok=True)

    src = work_path(cfg, "clean.field.jsonl")
    if not src.exists():
        raise SystemExit(
            f"{src} 가 없습니다. 먼저 실행하세요:\n"
            f"  python -m distill.prepare\n"
            f"  python -m distill.assign_field"
        )

    rows = read_jsonl(src)
    if args.limit:
        rows = (r for _, r in zip(range(args.limit), rows))

    teacher = Teacher(cfg)
    stats = collections.Counter()
    t0 = time.time()

    for shard_idx, batch in iter_shards(rows, cfg.teacher.shard_size):
        out = shard_path(labels_dir, shard_idx)
        if out.exists():
            print(f"샤드 {shard_idx:04d} 이미 있음 — 건너뜀")
            continue

        tone = teacher.label_tone(batch)

        merged = []
        for r, t in zip(batch, tone):
            row = {**r, **t}
            merged.append(row)
            stats["total"] += 1
            stats["tone_pass"] += int(t.get("tone_pass", False))
            stats[f"field_{r['field']}"] += 1

        write_jsonl(out, merged)
        elapsed = time.time() - t0
        rate = stats["total"] / max(elapsed, 1e-9)
        print(f"샤드 {shard_idx:04d} 저장 — 누적 {stats['total']:,}건 / "
              f"톤통과 {stats['tone_pass']:,} / {elapsed / 60:.1f}분 "
              f"({rate:.1f}건/초)")

    total = stats["total"]
    print(f"\n완료. 학습 가능(톤 게이트 통과): {stats['tone_pass']:,} / {total:,}"
          f"  ({stats['tone_pass'] / max(total, 1):.1%})")
    print("분야별:", {k[6:]: v for k, v in stats.items() if k.startswith("field_")})


if __name__ == "__main__":
    main()
