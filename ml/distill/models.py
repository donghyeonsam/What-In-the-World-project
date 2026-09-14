"""모델 정의 — 톤 student(인코더 + 헤드).

두 모델 모두 서비스(NLP worker)에서 그대로 로드해 쓴다.
저장 형식을 여기서 고정해 두면 worker 쪽 로더와 어긋나지 않는다.
"""
from __future__ import annotations

import json
from pathlib import Path

import torch
import torch.nn as nn
import torch.nn.functional as F
from transformers import AutoConfig, AutoModel


# =====================================================================
# 분야 분류기 — E5 임베딩(768) 위에 얹는 얕은 헤드
# =====================================================================
# =====================================================================
# 톤 student — 다국어 인코더 + sigmoid 2개
# =====================================================================
class ToneStudent(nn.Module):
    """인코더 → 풀링 → Linear(hidden, 2).

    출력 2개는 P(긍정), P(부정) 의 logit. softmax 가 아니라 각각 sigmoid 를 씌운다.
    그래야 "둘 다 높음(mixed)" 을 표현할 수 있다.
    """

    def __init__(self, model_name: str, pooling: str = "mean", dropout: float = 0.1) -> None:
        super().__init__()
        self.encoder = AutoModel.from_pretrained(model_name)
        hidden = self.encoder.config.hidden_size
        self.pooling = pooling
        self.head = nn.Sequential(nn.Dropout(dropout), nn.Linear(hidden, 2))
        self.model_name = model_name

    # Trainer 가 gradient_checkpointing=True 일 때 이 메서드를 부른다
    def gradient_checkpointing_enable(self, **kwargs) -> None:
        self.encoder.gradient_checkpointing_enable(**kwargs)

    def _pool(self, hidden: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        if self.pooling == "cls":
            return hidden[:, 0]
        # mean pooling — 긴 문서에서 CLS 하나보다 안정적
        m = mask.unsqueeze(-1).to(hidden.dtype)
        return (hidden * m).sum(1) / m.sum(1).clamp(min=1e-6)

    def forward(self, input_ids, attention_mask, labels=None):
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        pooled = self._pool(out.last_hidden_state, attention_mask)
        logits = self.head(pooled)                          # (B, 2)

        loss = None
        if labels is not None:
            # soft target BCE — teacher 확률(0~1 실수)을 그대로 타깃으로.
            # 0/1 로 바꾸면 teacher 의 확신도 정보가 사라진다.
            loss = F.binary_cross_entropy_with_logits(logits, labels.to(logits.dtype))
        return {"loss": loss, "logits": logits}

    @torch.no_grad()
    def predict_probs(self, input_ids, attention_mask) -> torch.Tensor:
        return torch.sigmoid(self(input_ids, attention_mask)["logits"])

    def save(self, dir_: Path, tokenizer, extra: dict | None = None) -> None:
        dir_ = Path(dir_)
        dir_.mkdir(parents=True, exist_ok=True)
        self.encoder.save_pretrained(dir_ / "encoder")
        tokenizer.save_pretrained(dir_ / "encoder")
        torch.save(self.head.state_dict(), dir_ / "head.pt")
        meta = {"model_name": self.model_name, "pooling": self.pooling,
                "hidden": self.encoder.config.hidden_size, **(extra or {})}
        (dir_ / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))

    @classmethod
    def load(cls, dir_: Path, device: str = "cpu") -> tuple["ToneStudent", dict]:
        dir_ = Path(dir_)
        meta = json.loads((dir_ / "meta.json").read_text())
        m = cls.__new__(cls)
        nn.Module.__init__(m)
        m.encoder = AutoModel.from_pretrained(dir_ / "encoder")
        m.pooling = meta["pooling"]
        m.model_name = meta["model_name"]
        m.head = nn.Sequential(nn.Dropout(0.0), nn.Linear(meta["hidden"], 2))
        m.head.load_state_dict(torch.load(dir_ / "head.pt", map_location=device))
        return m.to(device).eval(), meta


def resolve_student_model(model_name: str, fallback: str) -> tuple[str, int]:
    """mmBERT 로드 가능하면 그대로, 아니면 폴백. (모델명, 최대 길이) 반환."""
    try:
        conf = AutoConfig.from_pretrained(model_name)
        max_len = int(getattr(conf, "max_position_embeddings", 8192))
        return model_name, max_len
    except Exception as exc:                       # noqa: BLE001
        print(f"[경고] {model_name} 로드 실패 ({exc}) → 폴백 {fallback}")
        conf = AutoConfig.from_pretrained(fallback)
        return fallback, int(getattr(conf, "max_position_embeddings", 512))
