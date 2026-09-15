"""증류된 톤 student 로 기사 논조를 채점한다.  (nlp-worker/pipeline/tone_student.py)

teacher(NLI) 와 무엇이 다른가
  teacher 는 기사를 200 토큰 청크로 쪼개, 청크마다 긍정·부정 가설 6개를 물어
  entailment 확률을 받고, 극성차가 큰 상위 몇 개를 평균했다. 기사 1건에 수십 번 추론.

  student 는 기사 전체를 한 번에 보고 (p_pos, p_neg) 를 바로 낸다.
  청킹도 가설도 집계도 없다. 기사 1건에 추론 1회.

  → 기존 청크 경로(_chunk / _chunk_probs / agg_topk_mean)를 타면 안 된다.
    학습 때 본 적 없는 입력이 들어가 확률이 어긋난다. 그래서 ToneScorer 의
    내부를 고치는 대신, 같은 외부 계약을 가진 별도 클래스를 만들어 갈아끼운다.

학습과 반드시 같아야 하는 것
  · 텍스트 정제   tone-distill/distill/text.py 의 clean_text  ← 아래에 복사해 둠
  · 텍스트 구성   "제목\\n\\n본문"
  · 절단          max_length 초과 시 앞 head_tokens + 뒤 tail_tokens
  · 풀링          mean (attention_mask 가중)
  · 출력          sigmoid 2개 (softmax 아님 — mixed 를 표현해야 한다)

  정제 함수를 worker 의 것을 쓰지 않고 여기에 복사한 이유:
  학습 데이터는 tone-distill 의 clean_text 를 통과한 텍스트다. worker 의
  clean_text / strip_title_tail 은 규칙이 다르므로, 그걸 쓰면 train/serve 가
  어긋난다. 한 글자라도 학습 때와 같은 문자열을 넣는 쪽이 항상 맞다.

  절단도 마찬가지다. worker 의 MAX_BODY_CHARS(4000자)는 본문 앞쪽만 남기지만
  student 는 앞 1024 + 뒤 1024 토큰을 함께 보도록 학습됐다. 뉴스는 역피라미드라
  기자의 논평이 뒤에 붙는다. → 여기서는 글자 수로 미리 자르지 않는다.

디렉터리 구조 (tone-distill 이 저장한 work/models/tone/ 그대로)
    models/tone-student/
      POLITICS/  encoder/ + head.pt + meta.json
      ECONOMY/   ECONOMY/  SOCIETY/  TECH/  SPORTS/

환경변수
    TONE_STUDENT_DIR   기본 <worker>/models/tone-student
    TONE_BACKEND       "teacher" 로 두면 tone.py 가 student 를 건너뛴다(롤백용)
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
STUDENT_DIR = Path(os.getenv("TONE_STUDENT_DIR", str(MODELS_DIR / "tone-student")))

# 학습은 5개 분야로 했다. worker 의 resolve_category 는 theme 37/38 에
# "CULTURE" 를 돌려주는데 그 모델은 없다. 두 테마 모두 field 3(사회) 소속이므로
# SOCIETY 로 보낸다.
CATEGORY_ALIASES = {"CULTURE": "SOCIETY"}
FALLBACK_CATEGORY = "SOCIETY"


# =====================================================================
# 학습 때 쓴 정제 — tone-distill/distill/text.py 에서 그대로 복사
#   여기를 고치면 학습 코드도 같이 고쳐야 한다.
# =====================================================================
_BOILERPLATE = [
    # [데일리한국 정백현 기자] / （東京＝共同） 같은 머리표
    re.compile(
        r"^\s*[\[\(（【][^\]\)）】]{0,40}"
        r"(기자|특파원|뉴스|일보|신문|記者|通信|共同|時事)"
        r"[^\]\)）】]{0,20}[\]\)）】]\s*"
    ),
    # 이메일
    re.compile(r"[\w.\-+]+@[\w.\-]+\.[A-Za-z]{2,}"),
    # 저작권 문구 — 그 줄 끝까지
    re.compile(
        r"(저작권자|무단\s*전재|재배포\s*금지|All rights reserved|"
        r"Alle Rechte vorbehalten|無断転載|転載を禁じます)[^\n]*",
        re.I,
    ),
    # "관련기사" 이후는 다른 기사 제목 목록 — 전부 버림
    re.compile(
        r"\n\s*(관련\s*기사|関連記事|Read more|Mehr zum Thema|Lesen Sie auch|"
        r"あわせて読みたい)\b[\s\S]*$",
        re.I,
    ),
    # docomo 포털 제목 꼬리표
    re.compile(r"（[^）]{0,30}）\s*｜\s*ｄメニューニュース\s*$"),
]


def distill_clean_text(s: str | None) -> str:
    s = s or ""
    for pat in _BOILERPLATE:
        s = pat.sub("", s)
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def distill_build_text(title: str | None, body: str | None) -> str:
    title = (title or "").strip()
    body = (body or "").strip()
    return f"{title}\n\n{body}" if body else title


def _special_token_wrappers(tokenizer) -> tuple[list[int], list[int]]:
    """(앞 특수토큰, 뒤 특수토큰). 학습 코드와 동일한 방식으로 '관찰'해 얻는다.

    build_inputs_with_special_tokens / num_special_tokens_to_add 는 최신
    transformers 의 TokenizersBackend 에 없다(AttributeError). 그래서 묻지 않고,
    같은 문자열을 특수토큰 포함/미포함으로 인코딩해 앞뒤 차이를 본다.
    """
    with_sp = list(tokenizer("a", add_special_tokens=True)["input_ids"])
    without = list(tokenizer("a", add_special_tokens=False)["input_ids"])
    if not without or len(with_sp) < len(without):
        return [], []
    n = len(without)
    for i in range(len(with_sp) - n + 1):
        if with_sp[i:i + n] == without:
            return with_sp[:i], with_sp[i + n:]
    logger.warning("특수토큰 규약을 찾지 못해 없이 진행합니다 (학습과 어긋날 수 있음)")
    return [], []


class _FieldModel:
    """분야 하나의 student. encoder + head."""

    def __init__(self, dir_: Path, device: str) -> None:
        import torch
        import torch.nn as nn
        from transformers import AutoModel, AutoTokenizer

        self._torch = torch
        self.dir = dir_
        self.name = dir_.name
        self.meta = json.loads((dir_ / "meta.json").read_text(encoding="utf-8"))

        enc_dir = dir_ / "encoder"
        self.tokenizer = AutoTokenizer.from_pretrained(str(enc_dir))
        # eager: 학습 때와 같은 어텐션 경로.
        # ModernBERT 계열(mmBERT)은 sdpa 경로에서 bf16 + 패딩 마스크가 겹치면
        # softmax 가 전부 마스킹된 행을 만나 NaN 을 낸다(학습 중 5개 분야 전량 붕괴).
        # 추론은 배치 1 이라 패딩이 없지만, 학습과 같은 경로를 쓰는 편이 안전하다.
        try:
            self.encoder = AutoModel.from_pretrained(
                str(enc_dir), attn_implementation="eager")
        except (TypeError, ValueError) as exc:
            logger.warning("attn_implementation=eager 미지원 (%s) → 기본값", exc)
            self.encoder = AutoModel.from_pretrained(str(enc_dir))

        hidden = int(self.meta.get("hidden", self.encoder.config.hidden_size))
        self.head = nn.Sequential(nn.Dropout(0.0), nn.Linear(hidden, 2))
        try:
            state = torch.load(dir_ / "head.pt", map_location="cpu", weights_only=True)
        except TypeError:                       # torch < 2.0 에는 weights_only 가 없다
            state = torch.load(dir_ / "head.pt", map_location="cpu")
        self.head.load_state_dict(state)

        self.encoder.to(device).eval()
        self.head.to(device).eval()
        self.device = device

        self.pooling = str(self.meta.get("pooling", "mean"))
        self.max_length = int(self.meta.get("max_length", 2048))
        self.head_tokens = int(self.meta.get("head_tokens", 1024))
        self.tail_tokens = int(self.meta.get("tail_tokens", 1024))

        self.prefix, self.suffix = _special_token_wrappers(self.tokenizer)
        # 학습(ToneDataset.__init__)과 같은 보정: 특수토큰 자리를 빼고,
        # head + tail 이 상한을 넘지 않게 head 를 줄인다.
        self.body_max = self.max_length - len(self.prefix) - len(self.suffix)
        self.head_tokens = min(self.head_tokens,
                               max(self.body_max - self.tail_tokens, 1))

    def encode(self, text: str) -> list[int]:
        ids = list(self.tokenizer(text, add_special_tokens=False,
                                  truncation=False)["input_ids"])
        if len(ids) > self.body_max:
            ids = ids[:self.head_tokens] + ids[-self.tail_tokens:]
        return self.prefix + ids + self.suffix

    def probs(self, text: str) -> tuple[float, float]:
        torch = self._torch
        ids = self.encode(text)
        if not ids:
            return 0.0, 0.0

        input_ids = torch.tensor([ids], dtype=torch.long, device=self.device)
        mask = torch.ones_like(input_ids)

        with torch.no_grad():
            out = self.encoder(input_ids=input_ids, attention_mask=mask)
            h = out.last_hidden_state
            if self.pooling == "cls":
                pooled = h[:, 0]
            else:
                m = mask.unsqueeze(-1).to(h.dtype)
                pooled = (h * m).sum(1) / m.sum(1).clamp(min=1e-6)
            p = torch.sigmoid(self.head(pooled))[0].float().cpu().tolist()

        return float(p[0]), float(p[1])


class StudentToneScorer:
    """분야별 student 5개를 올려두고 category 로 라우팅한다.

    외부 계약은 기존 ToneScorer 와 같다 — score(title, body, category) -> dict.
    라벨 판정(decide_label)·톤 포인트 계산은 tone.py 의 make_sentiment 를 그대로
    재사용하므로, 하류(DB 컬럼·API 응답)에서 보이는 형태는 바뀌지 않는다.
    """

    def __init__(self, root: str | Path = STUDENT_DIR) -> None:
        import torch

        self.root = Path(root)
        if not self.root.is_dir():
            raise FileNotFoundError(f"student 디렉터리가 없습니다: {self.root}")

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.device == "cpu":
            logger.warning("Tone student 가 CPU 에서 돕니다 — 기사당 수 초 걸립니다")

        self.models: dict[str, _FieldModel] = {}
        for d in sorted(self.root.iterdir()):
            if not d.is_dir() or not (d / "meta.json").is_file():
                continue
            m = _FieldModel(d, self.device)
            self.models[d.name] = m
            logger.info("Tone student 로드: %s (max_length=%d head=%d tail=%d)",
                        d.name, m.max_length, m.head_tokens, m.tail_tokens)

        if not self.models:
            raise FileNotFoundError(f"student 모델을 찾지 못했습니다: {self.root}")

        self._lock = threading.Lock()   # worker 가 멀티스레드여도 안전하게
        self.model_name = "student:" + ",".join(sorted(self.models))

        self._selfcheck()
        logger.info("Tone student 준비 완료: %d개 분야 / device=%s",
                    len(self.models), self.device)

    # ---- 시작할 때 한 번만: tone.py 와의 계약이 맞는지 확인 ----------------
    def _selfcheck(self) -> None:
        """make_sentiment 시그니처가 기대와 다르면 '여기서' 터지게 한다.

        기동 직후에 알면 롤백이 쉽다. 기사 1만 건을 처리한 뒤 알면 늦다.
        """
        from .tone import make_sentiment
        out = make_sentiment(0.9, 0.1, model="selfcheck",
                             category=FALLBACK_CATEGORY, n_chunks=1)
        if not isinstance(out, dict):
            raise TypeError(f"make_sentiment 가 dict 를 돌려주지 않습니다: {type(out)}")

    def _pick(self, category: str | None) -> tuple[str, _FieldModel]:
        cat = CATEGORY_ALIASES.get(category or "", category or "")
        m = self.models.get(cat)
        if m is None:
            cat = (FALLBACK_CATEGORY if FALLBACK_CATEGORY in self.models
                   else sorted(self.models)[0])
            m = self.models[cat]
            logger.warning("category=%r 에 맞는 student 가 없어 %s 로 보냅니다",
                           category, cat)
        return cat, m

    def score(self, title: str | None = None, body: str | None = None,
              category: str | None = None, **_ignored: Any) -> dict[str, Any]:
        from .tone import make_sentiment

        used_cat, model = self._pick(category)

        # 학습과 같은 정제 → 같은 구성. 글자 수로 미리 자르지 않는다.
        text = distill_build_text(distill_clean_text(title),
                                  distill_clean_text(body))
        if not text:
            return make_sentiment(0.0, 0.0, model="empty",
                                  category=used_cat, n_chunks=0)

        with self._lock:
            p_pos, p_neg = model.probs(text)

        return make_sentiment(p_pos, p_neg, model=self.model_name,
                              category=used_cat, n_chunks=1)

    # sentiment.py 가 다른 이름으로 부르고 있다면 그 이름을 여기 alias 로 추가한다.
    score_article = score