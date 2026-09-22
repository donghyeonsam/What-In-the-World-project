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
import math
import random
import time

import numpy as np
import torch
from torch.utils.data import DataLoader, Dataset
from transformers import AutoTokenizer

from .config import load_config, work_path
from .io_utils import read_jsonl
from .models import ToneStudent, resolve_student_model
from .scoring import decide_label
from .text import build_text, head_tail


# =====================================================================
# 데이터셋
# =====================================================================
def special_token_wrappers(tokenizer) -> tuple[list[int], list[int]]:
    """(앞에 붙는 특수토큰, 뒤에 붙는 특수토큰) 을 돌려준다.

    왜 토크나이저 API 를 직접 안 쓰나
      build_inputs_with_special_tokens / num_special_tokens_to_add 는
      최신 transformers 의 TokenizersBackend 에 없다(AttributeError).
      모델마다 [CLS]/[SEP], <s>/</s>, 없음 등 규약도 다르다.

    그래서 토크나이저에 묻는 대신 관찰한다. 같은 문자열을 특수토큰 포함/미포함
    으로 인코딩해 앞뒤에 무엇이 덧붙는지 본다. 어느 백엔드에서도 동작한다.
    """
    probe = "a"
    with_sp = list(tokenizer(probe, add_special_tokens=True)["input_ids"])
    without = list(tokenizer(probe, add_special_tokens=False)["input_ids"])

    if not without or len(with_sp) < len(without):
        return [], []

    n = len(without)
    for i in range(len(with_sp) - n + 1):
        if with_sp[i:i + n] == without:
            return with_sp[:i], with_sp[i + n:]

    # 관찰 실패 — 특수토큰 없이 진행한다(학습은 되지만 모델 규약과 어긋날 수 있음)
    print("  [주의] 특수토큰 규약을 찾지 못해 없이 진행합니다")
    return [], []


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

        # 특수 토큰 자리를 빼고 절단 상한을 잡는다
        prefix, suffix = special_token_wrappers(tokenizer)
        body_max = max_length - len(prefix) - len(suffix)
        head = min(head, max(body_max - tail, 1))

        for r, ids in zip(rows, encoded):
            ids = prefix + head_tail(list(ids), body_max, head, tail) + suffix
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


# =====================================================================
# 학습 루프 — transformers Trainer 를 쓰지 않는다
#
#   Trainer 는 버전마다 인자와 내부 규약이 바뀐다. 실제로 이 환경에서
#   TrainingArguments(warmup_ratio=...) 가 TypeError 를 냈다.
#   여기서 필요한 것은 배치·누적·스케줄·평가뿐이고 전부 60줄이면 된다.
#   torch 만 쓰면 transformers 가 바뀌어도 학습이 안 깨진다.
# =====================================================================
def length_grouped_batches(lengths: list[int], batch_size: int,
                           rng: random.Random, mega: int = 50) -> list[list[int]]:
    """비슷한 길이끼리 묶어 패딩 낭비를 줄인다 (Trainer 의 group_by_length 대체).

    전부 길이순으로 정렬하면 매 에폭 같은 배치가 나와 학습이 나빠진다.
    큰 덩어리로 먼저 섞고, 그 안에서만 정렬한 뒤, 배치 순서를 다시 섞는다.
    """
    idx = list(range(len(lengths)))
    rng.shuffle(idx)
    chunk = batch_size * mega
    batches: list[list[int]] = []
    for i in range(0, len(idx), chunk):
        part = sorted(idx[i:i + chunk], key=lambda j: lengths[j])
        for k in range(0, len(part), batch_size):
            batches.append(part[k:k + batch_size])
    rng.shuffle(batches)
    return batches


def lr_at(step: int, total: int, warmup: int, base_lr: float) -> float:
    """선형 워밍업 후 선형 감쇠."""
    if warmup > 0 and step < warmup:
        return base_lr * step / max(warmup, 1)
    remain = max(total - warmup, 1)
    return base_lr * max(0.0, (total - step) / remain)


@torch.no_grad()
def evaluate_loss(model, ds, collate, device, batch_size, use_bf16) -> float:
    dev_type = "cuda" if str(device).startswith("cuda") else "cpu"
    model.eval()
    total, n = 0.0, 0
    for i in range(0, len(ds), batch_size):
        batch = collate([ds[j] for j in range(i, min(i + batch_size, len(ds)))])
        with torch.autocast(dev_type, dtype=torch.bfloat16, enabled=use_bf16):
            out = model(batch["input_ids"].to(device),
                        batch["attention_mask"].to(device),
                        labels=batch["labels"].to(device))
        total += float(out["loss"]) * len(batch["labels"])
        n += len(batch["labels"])
    return total / max(n, 1)


def run_training(model, train_ds, val_ds, collate, s, device, seed: int) -> None:
    use_bf16 = bool(s.bf16) and str(device).startswith("cuda")
    dev_type = "cuda" if str(device).startswith("cuda") else "cpu"
    model.to(device)
    if getattr(s, "gradient_checkpointing", False):
        model.gradient_checkpointing_enable()

    lengths = [it["length"] for it in train_ds.items]
    rng = random.Random(seed)
    accum = max(int(s.grad_accum), 1)
    nw = int(getattr(s, "num_workers", 0) or 0)

    n_batches = math.ceil(len(train_ds) / s.batch_size)
    total_steps = math.ceil(n_batches / accum) * int(s.epochs)
    warmup = int(total_steps * float(s.warmup_ratio))

    decay, no_decay = [], []
    for name, p in model.named_parameters():
        if not p.requires_grad:
            continue
        (no_decay if (p.ndim == 1 or name.endswith(".bias")) else decay).append(p)
    opt = torch.optim.AdamW(
        [{"params": decay, "weight_decay": float(s.weight_decay)},
         {"params": no_decay, "weight_decay": 0.0}],
        lr=float(s.lr),
    )

    print(f"  스텝 {total_steps:,} (배치 {s.batch_size} × 누적 {accum} × {s.epochs}에폭)"
          f" / 워밍업 {warmup:,} / bf16 {use_bf16} / dataloader worker {nw}")

    step = 0
    bad = 0                       # NaN 으로 건너뛴 배치 수
    max_bad = max(int(total_steps * 0.05), 20)
    t0 = time.time()
    for epoch in range(int(s.epochs)):
        model.train()
        batches = length_grouped_batches(lengths, int(s.batch_size), rng)
        running, seen = 0.0, 0
        opt.zero_grad(set_to_none=True)

        # 배치 준비(파이썬)와 GPU 연산을 겹쳐 돌린다.
        #   메인 프로세스에서 collate 하면 GPU 가 다음 배치를 기다리며 논다.
        #   실측: 사용률 7%, 스텝당 2.3초 → worker 프로세스로 넘겨 병렬화.
        loader = DataLoader(
            train_ds, batch_sampler=batches, collate_fn=collate,
            num_workers=nw, pin_memory=(dev_type == "cuda"),
            persistent_workers=False, prefetch_factor=(4 if nw else None),
        )

        for bi, batch in enumerate(loader):
            with torch.autocast(dev_type, dtype=torch.bfloat16, enabled=use_bf16):
                out = model(batch["input_ids"].to(device, non_blocking=True),
                            batch["attention_mask"].to(device, non_blocking=True),
                            labels=batch["labels"].to(device, non_blocking=True))
            loss = out["loss"]

            # --- NaN 방어 1: 손실이 유한한지 ---------------------------------
            #   NaN 이 한 번 역전파되면 가중치 전체가 NaN 이 되고 영구히 복구되지
            #   않는다. 실제로 이 방어가 없을 때 5개 분야 전부 망가졌다.
            #   역전파 '전에' 걸러내는 것이 핵심이다.
            if not torch.isfinite(loss):
                bad += 1
                L = int(batch["input_ids"].shape[1])
                if bad <= 3:
                    print(f"    [건너뜀] step {step:,} 부근 배치에서 loss={float(loss)} "
                          f"(배치 {tuple(batch['input_ids'].shape)}, 최대 길이 {L})",
                          flush=True)
                opt.zero_grad(set_to_none=True)
                if bad > max_bad:
                    raise RuntimeError(
                        f"NaN 배치가 {bad}개를 넘었습니다. bf16 을 끄거나 "
                        f"student.max_length 를 줄여야 합니다.")
                continue

            (loss / accum).backward()
            running += float(loss.detach())
            seen += 1

            if (bi + 1) % accum == 0 or bi == len(batches) - 1:
                gnorm = torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)

                # --- NaN 방어 2: 그래디언트가 유한한지 ------------------------
                #   손실이 멀쩡해도 역전파에서 터지는 경우가 있다.
                #   이때 opt.step() 을 태우면 가중치가 오염된다.
                if not torch.isfinite(gnorm):
                    bad += 1
                    if bad <= 3:
                        print(f"    [건너뜀] step {step:,} 그래디언트 norm={float(gnorm)}",
                              flush=True)
                    opt.zero_grad(set_to_none=True)
                    if bad > max_bad:
                        raise RuntimeError(f"NaN 그래디언트가 {bad}개를 넘었습니다.")
                    continue

                for g in opt.param_groups:
                    g["lr"] = lr_at(step, total_steps, warmup, float(s.lr))
                opt.step()
                opt.zero_grad(set_to_none=True)
                step += 1

                if step % 50 == 0:
                    el = time.time() - t0
                    eta = el / max(step, 1) * (total_steps - step)
                    print(f"    epoch {epoch + 1}/{s.epochs}  step {step:,}/{total_steps:,}"
                          f"  loss {running / max(seen, 1):.4f}"
                          f"  lr {opt.param_groups[0]['lr']:.2e}"
                          f"  경과 {el / 60:.1f}분  남은 {eta / 60:.1f}분", flush=True)
                    running, seen = 0.0, 0

        # 에폭 끝마다 가중치가 멀쩡한지 확인한다. 오염된 채로 계속 돌면
        # 남은 에폭이 통째로 낭비된다.
        nan_params = [n for n, p in model.named_parameters()
                      if not torch.isfinite(p).all()]
        if nan_params:
            raise RuntimeError(
                f"가중치가 NaN 이 되었습니다 (예: {nan_params[0]}). "
                f"이 상태로는 학습이 진행되지 않습니다.")

        vl = evaluate_loss(model, val_ds, collate, device,
                           int(s.batch_size) * 2, use_bf16)
        print(f"  [epoch {epoch + 1}] val loss {vl:.4f}"
              f"  (누적 {(time.time() - t0) / 60:.1f}분"
              f"{f' / NaN 건너뜀 {bad}개' if bad else ''})", flush=True)


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
    # pad_token 이 없는 토크나이저도 있다. 그 경우 eos/0 으로 대체한다.
    pad_id = getattr(tok, "pad_token_id", None)
    if pad_id is None:
        pad_id = getattr(tok, "eos_token_id", None) or 0
        print(f"  [주의] pad_token 이 없어 {pad_id} 로 패딩합니다")
    collate = make_collator(pad_id)

    lens = [it["length"] for it in train_ds.items]
    print(f"  토큰 길이 p50 {int(np.percentile(lens, 50))} / p95 {int(np.percentile(lens, 95))} / "
          f"절단 {sum(1 for l in lens if l >= max_length)}건")

    model = ToneStudent(model_name, pooling=s.pooling,
                        attn_implementation=getattr(s, "attn_implementation", "eager"))

    out_dir = cfg.data.work_dir / "models" / "tone" / field

    run_training(model, train_ds, val_ds, collate, s, device, cfg.split.seed)

    # ---- 언어별 평가 — 전체 평균에 묻히는 언어 성능 저하를 잡기 위해 ------
    probs = predict(model, val_ds, collate, device, int(s.batch_size) * 2)
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

    model.save(out_dir, tok, extra={
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