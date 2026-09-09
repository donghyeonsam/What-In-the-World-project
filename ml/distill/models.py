"""모델 정의. CategoryMLP(768→256→6) + ToneStudent(인코더 + 평균풀링 + 2로짓)."""
from __future__ import annotations

import torch
import torch.nn as nn


class CategoryMLP(nn.Module):
    """E5 임베딩 → 6개 분야.

    코사인 유사도가 아니라 '학습된' MLP다.
    nlp-worker의 코사인 버전은 학습 전 임시 구현이었다.
    """

    def __init__(self, in_dim: int = 768, hidden: int = 256,
                 n_classes: int = 6, dropout: float = 0.2):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_dim, hidden),
            nn.LayerNorm(hidden),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(hidden, n_classes),
        )
        self.in_dim = in_dim
        self.n_classes = n_classes

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


def mean_pool(hidden: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
    m = mask.unsqueeze(-1).to(hidden.dtype)
    return (hidden * m).sum(dim=1) / m.sum(dim=1).clamp(min=1e-9)


class ToneStudent(nn.Module):
    """다국어 인코더 + 2로짓(p_pos, p_neg). 분야별로 1개씩 학습한다.

    출력은 확률 2개뿐이다. 라벨은 scoring.decide_label이 로직으로 판정한다.
    두 로짓은 서로 경쟁하지 않는다(softmax 아님, BCE) — '둘 다 높음'이
    표현되어야 mixed가 가능하다.
    """

    def __init__(self, encoder, hidden_size: int, dropout: float = 0.1,
                 pooling: str = "mean"):
        super().__init__()
        self.encoder = encoder
        self.pooling = pooling
        self.dropout = nn.Dropout(dropout)
        self.head = nn.Linear(hidden_size, 2)

    def forward(self, input_ids: torch.Tensor, attention_mask: torch.Tensor,
                **kwargs) -> torch.Tensor:
        out = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        h = out.last_hidden_state
        if self.pooling == "cls":
            pooled = h[:, 0]
        else:
            pooled = mean_pool(h, attention_mask)
        return self.head(self.dropout(pooled))

    @torch.no_grad()
    def predict_proba(self, input_ids, attention_mask) -> torch.Tensor:
        return torch.sigmoid(self(input_ids, attention_mask))


def build_student(cfg) -> tuple[ToneStudent, object, int]:
    """(모델, 토크나이저, max_length). 로드 실패 시 폴백 + max_length 자동 축소."""
    from transformers import AutoConfig, AutoModel, AutoTokenizer

    st = cfg.student
    name, max_len = st["model"], int(st["max_length"])
    try:
        tok = AutoTokenizer.from_pretrained(name)
        enc = AutoModel.from_pretrained(name)
    except Exception as e:                                # noqa: BLE001
        name = st["fallback_model"]
        max_len = int(st["fallback_max_length"])
        print(f"[student] {st['model']} 로드 실패 ({type(e).__name__}) "
              f"→ 폴백 {name}, max_length={max_len}")
        tok = AutoTokenizer.from_pretrained(name)
        enc = AutoModel.from_pretrained(name)

    conf = AutoConfig.from_pretrained(name)
    limit = getattr(conf, "max_position_embeddings", max_len) or max_len
    if 0 < limit < max_len:
        print(f"[student] {name}의 위치 임베딩 상한 {limit} → max_length 축소")
        max_len = int(limit)

    if st.get("gradient_checkpointing") and hasattr(enc, "gradient_checkpointing_enable"):
        enc.gradient_checkpointing_enable()
    model = ToneStudent(enc, conf.hidden_size, pooling=st.get("pooling", "mean"))
    print(f"[student] {name} hidden={conf.hidden_size} max_length={max_len}")
    return model, tok, max_len
