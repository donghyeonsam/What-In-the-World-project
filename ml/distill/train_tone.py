"""[stage 4] 톤 student 학습 — 분야별 5개 → work/models/tone/{FIELD}/

teacher 가 청크를 나눠 집계한 (P긍정, P부정) 을 타깃으로,
student 는 기사 전체(최대 4,096 토큰)를 한 번에 보고 같은 값을 내도록 배운다.

  · 손실   : BCEWithLogits, soft target (teacher 확률 그대로)
  · 절단   : 4,096 초과 시 앞 3,072 + 뒤 1,024
  · 배치   : 길이가 비슷한 기사끼리 묶음 (group_by_length) — 패딩 낭비·메모리 절약
  · 메모리 : bf16 + gradient checkpointing

실행
    python -m distill.train_tone                  # 5개 전부
    python -m distill.train_tone --field ECONOMY  # 하나만
"""
from __future__ import annotations

import argparse
import collections

import numpy as np
import torch
from torch.utils.data import Dataset
from transformers import AutoTokenizer, Trainer, TrainingArguments

from .config import load_config, work_path
from .io_utils import read_jsonl
from .models import ToneStudent, resolve_student_model
from .scoring import decide_label
from .text import build_text, head_tail


# =====================================================================
# 데이터셋
# =====================================================================
class ToneDataset(Dataset):
    """토큰화를 __init__ 에서 한 번에 끝낸다.

    group_by_length 가 길이를 알아야 하고, 학습 중 매 스텝 토큰화하면 느리다.
    """

    def __init__(self, rows: list[dict], tokenizer, max_length: int, head: int, tail: int) -> None:
        self.rows = rows
        self.items: list[dict] = []

        texts = [build_text(r["title"], r["body"]) for r in rows]
        # 특수 토큰 없이 인코딩 → 절단 → 특수 토큰 부착. 절단이 [CLS]/[SEP] 을 먹지 않게.
        encoded = tokenizer(texts, add_special_tokens=False, truncation=False)["input_ids"]

        # 특수 토큰 자리(보통 2개)를 빼고 절단 상한을 잡는다
        n_special = tokenizer.num_special_tokens_to_add(pair=False)
        body_max = max_length - n_special
        head = min(head, body_max - tail)

        for r, ids in zip(rows, encoded):
            ids = head_tail(ids, body_max, head, tail)
            ids = tokenizer.build_inputs_with_special_tokens(ids)
            self.items.append({
                "input_ids": ids,
                "labels": [float(r["p_pos"]), float(r["p_neg"])],
                "length": len(ids),
            })

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, i: int) -> dict:
        return self.items[i]


def make_collator(pad_id: int):
    """배치 안에서 가장 긴 것에 맞춰 패딩. labels 는 (B, 2) float."""
    def collate(batch: list[dict]) -> dict:
        max_len = max(len(b["input_ids"]) for b in batch)
        ids = torch.full((len(batch), max_len), pad_id, dtype=torch.long)
        mask = torch.zeros((len(batch), max_len), dtype=torch.long)
        for i, b in enumerate(batch):
            n = len(b["input_ids"])
            ids[i, :n] = torch.tensor(b["input_ids"])
            mask[i, :n] = 1
        labels = torch.tensor([b["labels"] for b in batch], dtype=torch.float)
        return {"input_ids": ids, "attention_mask": mask, "labels": labels}
    return collate


# =====================================================================
# 평가 지표
# =====================================================================
def make_compute_metrics(lab):
    def compute_metrics(eval_pred):
        logits, targets = eval_pred
        probs = 1.0 / (1.0 + np.exp(-logits))                 # sigmoid
        mae = np.abs(probs - targets).mean()
        # teacher 라벨과 student 라벨 일치율 — 같은 임계값으로 판정
        t_lab = [decide_label(a, b, lab.mixed_threshold, lab.neutral_threshold) for a, b in targets]
        s_lab = [decide_label(a, b, lab.mixed_threshold, lab.neutral_threshold) for a, b in probs]
        agree = np.mean([t == s for t, s in zip(t_lab, s_lab)])
        return {"mae": float(mae), "label_agree": float(agree)}
    return compute_metrics


@torch.no_grad()
def predict(model: ToneStudent, ds: ToneDataset, collate, device: str, batch_size: int = 16) -> np.ndarray:
    model.eval()
    out = []
    for i in range(0, len(ds), batch_size):
        batch = collate([ds[j] for j in range(i, min(i + batch_size, len(ds)))])
        probs = model.predict_probs(batch["input_ids"].to(device), batch["attention_mask"].to(device))
        out.append(probs.float().cpu().numpy())
    return np.concatenate(out) if out else np.zeros((0, 2))


# =====================================================================
# 분야 하나 학습
# =====================================================================
def train_field(cfg, field: str, model_name: str, model_max: int) -> None:
    s = cfg.student
    lab = cfg.labels
    device = "cuda" if torch.cuda.is_available() else "cpu"

    train_rows = list(read_jsonl(work_path(cfg, "splits", field, "train.jsonl")))
    val_rows = list(read_jsonl(work_path(cfg, "splits", field, "val.jsonl")))
    if len(train_rows) < 50:
        print(f"[{field}] train {len(train_rows)}건 — 너무 적어 건너뜀")
        return

    max_length = min(s.max_length, model_max)
    print(f"\n[{field}] train {len(train_rows)} / val {len(val_rows)} / max_length {max_length}")

    tok = AutoTokenizer.from_pretrained(model_name)
    train_ds = ToneDataset(train_rows, tok, max_length, s.head_tokens, s.tail_tokens)
    val_ds = ToneDataset(val_rows, tok, max_length, s.head_tokens, s.tail_tokens)
    collate = make_collator(tok.pad_token_id)

    lens = [it["length"] for it in train_ds.items]
    print(f"  토큰 길이 p50 {int(np.percentile(lens, 50))} / p95 {int(np.percentile(lens, 95))} / "
          f"절단 {sum(1 for l in lens if l >= max_length)}건")

    model = ToneStudent(model_name, pooling=s.pooling)

    out_dir = cfg.data.work_dir / "models" / "tone" / field
    args = TrainingArguments(
        output_dir=str(out_dir / "_trainer"),
        num_train_epochs=s.epochs,
        learning_rate=s.lr,
        per_device_train_batch_size=s.batch_size,
        per_device_eval_batch_size=s.batch_size * 2,
        gradient_accumulation_steps=s.grad_accum,
        warmup_ratio=s.warmup_ratio,
        weight_decay=s.weight_decay,
        bf16=s.bf16 and device == "cuda",
        gradient_checkpointing=s.gradient_checkpointing,
        group_by_length=True,                 # 비슷한 길이끼리 배치 → 패딩·메모리 절약
        eval_strategy="epoch",
        save_strategy="no",                   # 저장은 아래에서 직접 (worker 로더 형식으로)
        logging_steps=20,
        report_to="none",
        remove_unused_columns=False,          # torch Dataset 이라 컬럼 제거 로직 불필요
        dataloader_num_workers=getattr(s, 'num_workers', 4),
        seed=cfg.split.seed,
    )
    trainer = Trainer(
        model=model, args=args,
        train_dataset=train_ds, eval_dataset=val_ds,
        data_collator=collate,
        compute_metrics=make_compute_metrics(lab),
    )
    trainer.train()

    # ---- 언어별 평가 — 전체 평균에 묻히는 언어 성능 저하를 잡기 위해 ------
    probs = predict(trainer.model, val_ds, collate, device)
    targets = np.array([[r["p_pos"], r["p_neg"]] for r in val_rows])
    langs = np.array([r["lang"] for r in val_rows])

    print(f"\n  [{field}] 언어별 (val)")
    print(f"    {'언어':<6}{'n':>6}{'MAE':>8}{'라벨일치':>10}")
    per_lang = {}
    for lang in sorted(set(langs)):
        m = langs == lang
        mae = float(np.abs(probs[m] - targets[m]).mean())
        t_lab = [decide_label(a, b, lab.mixed_threshold, lab.neutral_threshold) for a, b in targets[m]]
        s_lab = [decide_label(a, b, lab.mixed_threshold, lab.neutral_threshold) for a, b in probs[m]]
        agree = float(np.mean([t == s for t, s in zip(t_lab, s_lab)]))
        per_lang[lang] = {"n": int(m.sum()), "mae": round(mae, 4), "label_agree": round(agree, 4)}
        print(f"    {lang:<6}{m.sum():>6}{mae:>8.4f}{agree:>10.4f}")

    # 라벨 분포 — student 가 한쪽으로 몰리지 않았는지
    s_labels = collections.Counter(decide_label(a, b, lab.mixed_threshold, lab.neutral_threshold) for a, b in probs)
    print(f"  student 라벨 분포: {dict(s_labels)}")

    trainer.model.save(out_dir, tok, extra={
        "field": field, "max_length": max_length,
        "head_tokens": s.head_tokens, "tail_tokens": s.tail_tokens,
        "val_per_lang": per_lang,
        "mixed_threshold": lab.mixed_threshold, "neutral_threshold": lab.neutral_threshold,
    })
    print(f"  저장: {out_dir}")


def field_names(cfg) -> list[str]:
    """config.fields 를 순서대로 이름 리스트로. {1: 'POLITICS', ...} 또는 리스트."""
    f = cfg.fields
    if isinstance(f, dict):
        return [f[k] for k in sorted(int(x) for x in f)]
    return list(f)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--field", default=None, help="분야 하나만 (미지정 시 전부)")
    args = ap.parse_args()

    cfg = load_config()
    names = field_names(cfg)

    if args.field and args.field not in names:
        raise SystemExit(f"알 수 없는 분야: {args.field}\n선택지: {', '.join(names)}")

    model_name, model_max = resolve_student_model(cfg.student.model, cfg.student.fallback_model)
    print(f"student 베이스: {model_name} (max {model_max})")

    fields = [args.field] if args.field else names
    print(f"학습 대상 {len(fields)}개: {', '.join(fields)}")

    failed = []
    for d in fields:
        try:
            train_field(cfg, d, model_name, model_max)
        except Exception as exc:
            # 한 분야가 실패해도 나머지는 계속한다. 재실행 기능이 없으므로
            # 전부 날리는 것보다 낫다.
            print(f"\n[{d}] 실패: {type(exc).__name__}: {exc}", flush=True)
            import traceback
            traceback.print_exc()
            failed.append(d)

    if failed:
        print(f"\n실패한 분야 {len(failed)}개: {', '.join(failed)}")
        print(f"  다시 돌리려면: python -u -m distill.train_tone --field {failed[0]}")
    else:
        print(f"\n전체 완료 — {cfg.data.work_dir / 'models' / 'tone'}")


if __name__ == "__main__":
    main()