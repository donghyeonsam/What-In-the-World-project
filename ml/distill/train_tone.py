"""[4] 톤 student 6개 학습 (분야별 1개) → 산출물 B

python -m distill.train_tone [--only ECONOMY TECH]

입력: work/train.jsonl, work/val.jsonl
출력: artifacts/tone/<CATEGORY>/{model.pt, meta.json}

손실은 소프트 타깃 BCEWithLogitsLoss다. teacher 확률이 그대로 타깃이며
0/1이 아니다. student가 배우는 건 정답표가 아니라 '0.88이라는 숫자 자체'다.
"""
from __future__ import annotations

import argparse
import json
import math

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

from .config import load_config, out_path, work_path
from .io_utils import read_jsonl
from .models import build_student
from .scoring import decide_label, tone_point
from .text import head_tail_ids


class ToneDataset(Dataset):
    """__init__에서 토크나이즈한다 (특수토큰 제거 → 자르기 → 재부착)."""

    def __init__(self, rows: list[dict], tok, max_length: int,
                 head_tokens: int, tail_tokens: int, max_body_chars: int):
        self.items: list[dict] = []
        cls, sep = tok.cls_token_id, tok.sep_token_id
        n_special = int(cls is not None) + int(sep is not None)
        budget = max_length - n_special
        head = min(head_tokens, budget)
        tail = min(tail_tokens, max(0, budget - head))
        for r in rows:
            text = f"{r['title']}\n\n{r['body'][:max_body_chars]}"
            ids = tok.encode(text, add_special_tokens=False)
            ids = head_tail_ids(ids, budget, head, tail)
            if cls is not None:
                ids = [cls] + ids
            if sep is not None:
                ids = ids + [sep]
            s = r["sentiment"]
            self.items.append({
                "ids": ids,
                "target": [float(s["p_pos"]), float(s["p_neg"])],
                "lang": r["lang"], "id": r["id"],
                "label": s["label"], "score": float(s["score"]),
                "n": len(ids),
            })

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, i: int) -> dict:
        return self.items[i]

    def lengths(self) -> list[int]:
        return [it["n"] for it in self.items]


def collate(batch: list[dict], pad_id: int) -> dict:
    n = max(b["n"] for b in batch)
    ids = torch.full((len(batch), n), pad_id, dtype=torch.long)
    mask = torch.zeros((len(batch), n), dtype=torch.long)
    for i, b in enumerate(batch):
        ids[i, :b["n"]] = torch.tensor(b["ids"], dtype=torch.long)
        mask[i, :b["n"]] = 1
    return {
        "input_ids": ids, "attention_mask": mask,
        "target": torch.tensor([b["target"] for b in batch], dtype=torch.float32),
        "lang": [b["lang"] for b in batch],
        "label": [b["label"] for b in batch],
    }


def length_grouped_batches(lengths: list[int], batch_size: int,
                           generator: torch.Generator) -> list[list[int]]:
    """group_by_length. 긴 시퀀스에서 패딩 낭비를 줄인다."""
    idx = torch.randperm(len(lengths), generator=generator).tolist()
    mega = batch_size * 50
    out: list[list[int]] = []
    for i in range(0, len(idx), mega):
        block = sorted(idx[i:i + mega], key=lambda j: lengths[j])
        out.extend(block[j:j + batch_size] for j in range(0, len(block), batch_size))
    order = torch.randperm(len(out), generator=generator).tolist()
    return [out[i] for i in order]


@torch.no_grad()
def evaluate_split(model, loader, device) -> dict:
    model.eval()
    per_lang: dict = {}
    mae_all, lab_ok, n = [], 0, 0
    for b in loader:
        p = torch.sigmoid(model(b["input_ids"].to(device),
                                b["attention_mask"].to(device))).float().cpu().numpy()
        tgt = b["target"].numpy()
        for i in range(len(p)):
            pp, pn = float(p[i, 0]), float(p[i, 1])
            tp, tn = float(tgt[i, 0]), float(tgt[i, 1])
            mae = abs(tone_point(pp, pn) - tone_point(tp, tn))
            ok = int(decide_label(pp, pn) == b["label"][i])
            mae_all.append(mae)
            lab_ok += ok
            n += 1
            d = per_lang.setdefault(b["lang"][i], {"mae": [], "ok": 0, "n": 0})
            d["mae"].append(mae)
            d["ok"] += ok
            d["n"] += 1
    return {
        "point_mae": round(float(np.mean(mae_all)), 3) if mae_all else None,
        "label_agree": round(lab_ok / n, 4) if n else None,
        "n": n,
        "by_lang": {k: {"point_mae": round(float(np.mean(v["mae"])), 3),
                        "label_agree": round(v["ok"] / v["n"], 4), "n": v["n"]}
                    for k, v in sorted(per_lang.items())},
    }


def train_one(category: str, tr_rows: list[dict], va_rows: list[dict], cfg) -> dict:
    st = cfg.student
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model, tok, max_len = build_student(cfg)
    model.to(device)
    mbc = int(cfg.category_clf["max_body_chars"])

    ds_tr = ToneDataset(tr_rows, tok, max_len, int(st["head_tokens"]),
                        int(st["tail_tokens"]), mbc)
    ds_va = ToneDataset(va_rows, tok, max_len, int(st["head_tokens"]),
                        int(st["tail_tokens"]), mbc)
    pad = tok.pad_token_id if tok.pad_token_id is not None else 0
    va_loader = DataLoader(ds_va, batch_size=int(st["batch_size"]), shuffle=False,
                           collate_fn=lambda b: collate(b, pad)) if len(ds_va) else None

    bs, ga = int(st["batch_size"]), int(st["grad_accum"])
    epochs = int(st["epochs"])
    steps = math.ceil(len(ds_tr) / bs / ga) * epochs
    opt = torch.optim.AdamW(model.parameters(), lr=float(st["lr"]),
                            weight_decay=float(st.get("weight_decay", 0.01)))
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=float(st["lr"]), total_steps=max(1, steps),
        pct_start=float(st.get("warmup_ratio", 0.1)), anneal_strategy="cos")
    lossf = nn.BCEWithLogitsLoss()               # 소프트 타깃
    use_bf16 = bool(st.get("bf16")) and device == "cuda" and \
        torch.cuda.is_bf16_supported()
    gen = torch.Generator().manual_seed(int(cfg.get("seed", 42)))
    lengths = ds_tr.lengths()

    print(f"\n=== [{category}] train {len(ds_tr):,} / val {len(ds_va):,} "
          f"토큰 중위 {int(np.median(lengths))} 최대 {max(lengths)} bf16={use_bf16}")

    for ep in range(1, epochs + 1):
        model.train()
        batches = (length_grouped_batches(lengths, bs, gen)
                   if st.get("group_by_length", True)
                   else [list(range(i, min(i + bs, len(ds_tr))))
                         for i in range(0, len(ds_tr), bs)])
        opt.zero_grad()
        run_loss, seen = 0.0, 0
        for k, bidx in enumerate(batches, 1):
            b = collate([ds_tr[i] for i in bidx], pad)
            ctx = (torch.autocast("cuda", dtype=torch.bfloat16) if use_bf16
                   else torch.autocast("cpu", enabled=False))
            with ctx:
                logits = model(b["input_ids"].to(device), b["attention_mask"].to(device))
                loss = lossf(logits.float(), b["target"].to(device))
            (loss / ga).backward()
            if k % ga == 0 or k == len(batches):
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                sched.step()
                opt.zero_grad()
            run_loss += float(loss) * len(bidx)
            seen += len(bidx)
            if k % 50 == 0:
                print(f"  ep{ep} {k}/{len(batches)} loss={run_loss/seen:.4f}", flush=True)
        line = f"  ep{ep} train_loss={run_loss/max(1,seen):.4f}"
        if va_loader:
            m = evaluate_split(model, va_loader, device)
            line += f" val_mae={m['point_mae']} val_agree={m['label_agree']}"
        print(line, flush=True)

    metrics = evaluate_split(model, va_loader, device) if va_loader else {}
    d = out_path(cfg, "tone", category, "model.pt").parent
    torch.save(model.state_dict(), d / "model.pt")
    meta = {
        "category": category,
        "base_model": getattr(model.encoder.config, "_name_or_path", st["model"]),
        "max_length": max_len,
        "head_tokens": int(st["head_tokens"]), "tail_tokens": int(st["tail_tokens"]),
        "pooling": st.get("pooling", "mean"),
        "loss": "BCEWithLogitsLoss(soft targets)",
        "n_train": len(ds_tr), "n_val": len(ds_va),
        "metrics": metrics,
    }
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    print(f"  → {d} / 언어별: {metrics.get('by_lang')}")
    return meta


def run(cfg, only: list[str] | None = None) -> dict:
    tr = list(read_jsonl(work_path(cfg, "train.jsonl")))
    va = list(read_jsonl(work_path(cfg, "val.jsonl")))
    if not tr:
        raise SystemExit("train.jsonl이 비었음. 먼저 python -m distill.split 실행")

    cats = [c for c in cfg.categories if not only or c in only]
    min_n = int(cfg.student.get("min_train_per_category", 50))
    summary: dict = {}
    for c in cats:
        t = [r for r in tr if r["category"] == c]
        v = [r for r in va if r["category"] == c]
        if len(t) < min_n:
            print(f"\n=== [{c}] train {len(t)} < {min_n} → 건너뜀 (수집 확대 필요)")
            summary[c] = {"skipped": True, "n_train": len(t)}
            continue
        summary[c] = train_one(c, t, v, cfg)

    p = out_path(cfg, "tone", "summary.json")
    p.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[tone] {sum(1 for v in summary.values() if not v.get('skipped'))}"
          f"/{len(cats)}개 학습 완료 → {p}")
    return summary


def main() -> None:
    ap = argparse.ArgumentParser(description="[4] 톤 student 학습")
    ap.add_argument("--config", default=None)
    ap.add_argument("--only", nargs="*", default=None, help="특정 분야만")
    a = ap.parse_args()
    run(load_config(a.config), only=a.only)


if __name__ == "__main__":
    main()
