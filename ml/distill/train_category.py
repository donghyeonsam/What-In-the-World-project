"""[3] 분야 분류기 학습 → 산출물 A + centroid.npy

python -m distill.train_category

입력: work/train.jsonl, work/val.jsonl
출력: artifacts/category/{model.pt, centroid.npy, meta.json}

E5 임베딩은 mean-centering이 필수다. 비등방성(anisotropy) 때문에
무관한 쌍의 코사인 유사도 p99가 0.80까지 뜬다. 중심화하면 0.24로 떨어진다.
→ centroid.npy를 모델과 함께 저장하고 런타임에서도 같은 값을 빼야 한다.
"""
from __future__ import annotations

import argparse
import json

import numpy as np
import torch
import torch.nn as nn

from .config import load_config, out_path, work_path
from .io_utils import read_jsonl
from .models import CategoryMLP


def embed_texts(texts: list[str], cfg, device: str) -> np.ndarray:
    from transformers import AutoModel, AutoTokenizer

    cc = cfg.category_clf
    name = cc["embed_model"]
    tok = AutoTokenizer.from_pretrained(name)
    enc = AutoModel.from_pretrained(name).to(device).eval()
    bs = int(cc["embed_batch_size"])
    prefix = cc.get("embed_prefix", "passage: ")
    out = []
    with torch.no_grad():
        for i in range(0, len(texts), bs):
            batch = [prefix + t for t in texts[i:i + bs]]
            e = tok(batch, return_tensors="pt", padding=True, truncation=True,
                    max_length=int(cc.get("embed_max_length", 512)))
            e = {k: v.to(device) for k, v in e.items()}
            h = enc(**e).last_hidden_state
            m = e["attention_mask"].unsqueeze(-1).to(h.dtype)
            pooled = (h * m).sum(1) / m.sum(1).clamp(min=1e-9)
            out.append(pooled.float().cpu().numpy())
            if (i // bs) % 20 == 0:
                print(f"  embed {i:,}/{len(texts):,}", flush=True)
    return np.concatenate(out, axis=0)


def make_input_text(rec: dict, max_body_chars: int) -> str:
    """NLP worker와 동일한 규칙이어야 한다 (max_body_chars 포함)."""
    return f"{rec['title']}\n\n{rec['body'][:max_body_chars]}"


def normalize(x: np.ndarray, centroid: np.ndarray | None) -> np.ndarray:
    if centroid is not None:
        x = x - centroid
    n = np.linalg.norm(x, axis=1, keepdims=True)
    return x / np.clip(n, 1e-9, None)


def run(cfg) -> dict:
    cats = list(cfg.categories)
    cc = cfg.category_clf
    device = "cuda" if torch.cuda.is_available() else "cpu"
    mbc = int(cc["max_body_chars"])

    tr = list(read_jsonl(work_path(cfg, "train.jsonl")))
    va = list(read_jsonl(work_path(cfg, "val.jsonl")))
    if not tr:
        raise SystemExit("train.jsonl이 비었음. 먼저 python -m distill.split 실행")
    print(f"[category] train {len(tr):,} / val {len(va):,} device={device}")

    Xtr = embed_texts([make_input_text(r, mbc) for r in tr], cfg, device)
    Xva = embed_texts([make_input_text(r, mbc) for r in va], cfg, device) \
        if va else np.zeros((0, Xtr.shape[1]), dtype=np.float32)

    # --- mean-centering: 학습셋에서 중심을 구하고 저장 ---------------------
    centroid = Xtr.mean(axis=0) if cc.get("mean_center", True) else None
    if centroid is not None:
        raw = normalize(Xtr[:200], None)
        cen = normalize(Xtr[:200], centroid)
        def p99(z):
            s = z @ z.T
            iu = np.triu_indices_from(s, k=1)
            return float(np.percentile(s[iu], 99))
        print(f"  비등방성 점검: 코사인 p99 {p99(raw):.3f} → 중심화 후 {p99(cen):.3f}")

    Xtr, Xva = normalize(Xtr, centroid), normalize(Xva, centroid)
    ytr = np.array([cats.index(r["category"]) for r in tr])
    yva = np.array([cats.index(r["category"]) for r in va]) if va else np.zeros(0, int)

    model = CategoryMLP(Xtr.shape[1], int(cc["hidden"]), len(cats),
                        float(cc["dropout"])).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=float(cc["lr"]))
    lossf = nn.CrossEntropyLoss()
    Xt = torch.tensor(Xtr, dtype=torch.float32, device=device)
    Yt = torch.tensor(ytr, dtype=torch.long, device=device)
    Xv = torch.tensor(Xva, dtype=torch.float32, device=device)
    Yv = torch.tensor(yva, dtype=torch.long, device=device)

    bs = int(cc.get("batch_size", 64))
    best, best_state, bad = -1.0, None, 0
    for ep in range(1, int(cc["epochs"]) + 1):
        model.train()
        perm = torch.randperm(len(Xt), device=device)
        tot = 0.0
        for i in range(0, len(perm), bs):
            idx = perm[i:i + bs]
            opt.zero_grad()
            loss = lossf(model(Xt[idx]), Yt[idx])
            loss.backward()
            opt.step()
            tot += float(loss) * len(idx)
        model.eval()
        with torch.no_grad():
            acc = float((model(Xv).argmax(1) == Yv).float().mean()) if len(Xv) else 0.0
        print(f"  ep{ep:02d} loss={tot/len(Xt):.4f} val_acc={acc:.4f}")
        if acc > best:
            best, bad = acc, 0
            best_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
        else:
            bad += 1
            if bad >= int(cc["patience"]):
                print(f"  early stop (patience {cc['patience']})")
                break
    if best_state:
        model.load_state_dict(best_state)

    # --- 언어별 정확도 ----------------------------------------------------
    per_lang: dict = {}
    if va:
        model.eval()
        with torch.no_grad():
            pred = model(Xv).argmax(1).cpu().numpy()
        for lg in sorted({r["lang"] for r in va}):
            m = np.array([r["lang"] == lg for r in va])
            per_lang[lg] = round(float((pred[m] == yva[m]).mean()), 4)
        print(f"  언어별 val_acc: {per_lang}")

    d = out_path(cfg, "category", "model.pt").parent
    torch.save(model.state_dict(), d / "model.pt")
    if centroid is not None:
        np.save(d / "centroid.npy", centroid.astype(np.float32))
    meta = {
        "categories": cats,
        "embed_model": cc["embed_model"],
        "embed_prefix": cc.get("embed_prefix", "passage: "),
        "max_body_chars": mbc,
        "in_dim": int(Xtr.shape[1]), "hidden": int(cc["hidden"]),
        "dropout": float(cc["dropout"]),
        "mean_center": bool(centroid is not None),
        "val_acc": round(best, 4), "val_acc_by_lang": per_lang,
        "n_train": len(tr), "n_val": len(va),
    }
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2),
                                 encoding="utf-8")
    print(f"[category] val_acc={best:.4f} → {d}")
    print("  ⚠ centroid.npy를 nlp-worker conf/ 로 복사해야 함 "
          "(런타임에서 같은 값을 빼지 않으면 조용히 정확도만 떨어진다)")
    return meta


def main() -> None:
    ap = argparse.ArgumentParser(description="[3] 분야 분류기 학습")
    ap.add_argument("--config", default=None)
    a = ap.parse_args()
    run(load_config(a.config))


if __name__ == "__main__":
    main()
