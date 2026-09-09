"""[5] 평가. 분야 분류기 + 톤 student 6개를 val에서 이어 돌린다.

python -m distill.evaluate

teacher 라벨을 기준으로 student의 재현도를 본다 (사람 정답이 아님).
언어별로 따로 출력한다 — 4개 언어 중 하나만 무너져도 서비스에서는 그 나라 색이 틀린다.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict

import numpy as np
import torch

from .config import load_config, out_path, work_path
from .io_utils import read_jsonl
from .models import CategoryMLP, build_student
from .scoring import decide_label, tone_point
from .train_category import embed_texts, make_input_text, normalize
from .train_tone import ToneDataset, collate


def eval_category(rows: list[dict], cfg, device: str) -> dict:
    d = out_path(cfg, "category", "meta.json").parent
    if not (d / "model.pt").exists():
        return {"skipped": "artifacts/category/model.pt 없음"}
    meta = json.loads((d / "meta.json").read_text(encoding="utf-8"))
    cats = meta["categories"]
    X = embed_texts([make_input_text(r, meta["max_body_chars"]) for r in rows],
                    cfg, device)
    cen = np.load(d / "centroid.npy") if meta.get("mean_center") else None
    X = normalize(X, cen)
    model = CategoryMLP(meta["in_dim"], meta["hidden"], len(cats),
                        meta["dropout"]).to(device)
    model.load_state_dict(torch.load(d / "model.pt", map_location=device))
    model.eval()
    with torch.no_grad():
        pred = model(torch.tensor(X, dtype=torch.float32, device=device)).argmax(1).cpu().numpy()
    y = np.array([cats.index(r["category"]) for r in rows])
    per_lang, per_cat = {}, {}
    for lg in sorted({r["lang"] for r in rows}):
        m = np.array([r["lang"] == lg for r in rows])
        per_lang[lg] = round(float((pred[m] == y[m]).mean()), 4)
    for i, c in enumerate(cats):
        m = y == i
        if m.any():
            per_cat[c] = round(float((pred[m] == y[m]).mean()), 4)
    return {"accuracy": round(float((pred == y).mean()), 4),
            "by_lang": per_lang, "by_category": per_cat, "n": len(rows)}


def eval_tone(rows: list[dict], cfg, device: str) -> dict:
    st = cfg.student
    mbc = int(cfg.category_clf["max_body_chars"])
    out: dict = {}
    for c in cfg.categories:
        d = out_path(cfg, "tone", c, "model.pt").parent
        sub = [r for r in rows if r["category"] == c]
        if not (d / "model.pt").exists() or not sub:
            out[c] = {"skipped": True, "n": len(sub)}
            continue
        model, tok, max_len = build_student(cfg)
        model.load_state_dict(torch.load(d / "model.pt", map_location="cpu"))
        model.to(device).eval()
        ds = ToneDataset(sub, tok, max_len, int(st["head_tokens"]),
                         int(st["tail_tokens"]), mbc)
        pad = tok.pad_token_id if tok.pad_token_id is not None else 0
        agg: dict = defaultdict(lambda: {"mae": [], "ok": 0, "n": 0})
        conf: dict = defaultdict(int)
        for i in range(0, len(ds), int(st["batch_size"])):
            b = collate([ds[j] for j in range(i, min(i + int(st["batch_size"]), len(ds)))], pad)
            with torch.no_grad():
                p = torch.sigmoid(model(b["input_ids"].to(device),
                                        b["attention_mask"].to(device))).float().cpu().numpy()
            t = b["target"].numpy()
            for k in range(len(p)):
                pred = decide_label(float(p[k, 0]), float(p[k, 1]))
                mae = abs(tone_point(*p[k]) - tone_point(*t[k]))
                for key in ("ALL", b["lang"][k]):
                    a = agg[key]
                    a["mae"].append(mae)
                    a["ok"] += int(pred == b["label"][k])
                    a["n"] += 1
                conf[f"{b['label'][k]}→{pred}"] += 1
        out[c] = {
            "n": len(ds),
            "point_mae": round(float(np.mean(agg["ALL"]["mae"])), 3),
            "label_agree": round(agg["ALL"]["ok"] / agg["ALL"]["n"], 4),
            "by_lang": {k: {"point_mae": round(float(np.mean(v["mae"])), 3),
                            "label_agree": round(v["ok"] / v["n"], 4), "n": v["n"]}
                        for k, v in sorted(agg.items()) if k != "ALL"},
            "confusion": dict(sorted(conf.items(), key=lambda kv: -kv[1])[:8]),
        }
        print(f"  [{c}] mae={out[c]['point_mae']} agree={out[c]['label_agree']} "
              f"{out[c]['by_lang']}")
    return out


def run(cfg) -> dict:
    rows = list(read_jsonl(work_path(cfg, "val.jsonl")))
    if not rows:
        raise SystemExit("val.jsonl이 비었음")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"[evaluate] val {len(rows):,} device={device}")
    print("\n분야 분류기")
    cat = eval_category(rows, cfg, device)
    print(f"  {cat}")
    print("\n톤 student")
    tone = eval_tone(rows, cfg, device)
    rep = {"n_val": len(rows), "category": cat, "tone": tone}
    p = out_path(cfg, "evaluation.json")
    p.write_text(json.dumps(rep, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {p}")
    return rep


def main() -> None:
    ap = argparse.ArgumentParser(description="[5] 평가")
    ap.add_argument("--config", default=None)
    a = ap.parse_args()
    run(load_config(a.config))


if __name__ == "__main__":
    main()
