"""
기사 논조(톤)를 긍정/부정 확률로 채점하는 모듈.

- teacher 모델(NLI zero-shot)을 그대로 사용한다. 학습이 필요 없다.
- 다음 주에 증류된 student로 교체할 때 ToneScorer._chunk_probs 만 갈아끼우면 된다.
  외부 계약(score_article 반환 형태)은 student 교체 후에도 동일하다.
- field_id(1~5)에 따라 가설 문장을 바꾼다. 같은 표현이 분야마다 논조가 다르기
  때문이다. "격차가 벌어졌다"는 경제에서 부정이지만 스포츠에서는 경기 결과다.
- 모델 로드 실패 시 예외를 던지지 않고 dummy(50.0)로 폴백한다. 톤 모델 때문에
  파이프라인 전체가 멈추면 안 된다. 폴백 여부는 반환값의 model 필드로 구분한다.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# --- 모델 위치 --------------------------------------------------------------
# language.py의 models/lid.176.bin 규약을 따른다. 컨테이너의 /app/models 는
# 호스트의 nlp-worker/models 를 마운트한 것이므로, 가중치는 이미지에 넣지 않고
# 서버의 models/ 에 올려 두고 참조한다.
#
#   nlp-worker/models/
#     ├── lid.176.bin            (기존 fastText)
#     ├── tone-teacher/          ← 이번에 올릴 것
#     └── tone-student/          (다음 주. 분야별 하위 디렉터리 6개)
#
# 디렉터리가 있으면 오프라인으로 로드하고, 없으면 HF 이름으로 폴백한다
# (로컬 개발 편의. GPU 서버에서는 항상 로컬 디렉터리를 쓰는 것을 전제로 한다).
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
TONE_MODEL_DIR = Path(os.getenv("TONE_MODEL_DIR", str(MODELS_DIR / "tone-teacher")))
MODEL_NAME = os.getenv(
    "TONE_MODEL_NAME",
    "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7",
)
# 로컬 디렉터리가 없을 때 HF 다운로드를 허용할지. GPU 서버는 0 권장.
TONE_ALLOW_DOWNLOAD = os.getenv("TONE_ALLOW_DOWNLOAD", "1") not in ("0", "false", "False")
# 비활성화하면 기존 dummy 동작(50.0)을 그대로 유지한다. 롤백 스위치.
TONE_ENABLED = os.getenv("TONE_ENABLED", "1") not in ("0", "false", "False")


def resolve_model_source() -> tuple[str, bool]:
    """(로드에 쓸 경로/이름, local_files_only) 를 돌려준다.

    local_files_only=True 로 넘겨야 디렉터리가 불완전할 때 조용히 네트워크로
    새지 않고 즉시 실패한다.
    """
    config = TONE_MODEL_DIR / "config.json"
    if config.is_file():
        return str(TONE_MODEL_DIR), True
    if not TONE_ALLOW_DOWNLOAD:
        raise FileNotFoundError(
            f"tone model not found: {config} "
            f"(TONE_ALLOW_DOWNLOAD=0 이므로 다운로드하지 않는다. "
            f"scripts/download_tone_model.py 로 미리 내려받을 것)"
        )
    return MODEL_NAME, False

MODEL_MAX_TOKENS = 512          # mDeBERTa 상한. 올리면 조용히 잘린다.
CHUNK_TOKENS = 200              # 청크 하나의 예산
MIN_CHUNK_TOKENS = 20           # 이보다 짧은 꼬리 청크는 직전 청크에 흡수
MAX_CHUNKS = int(os.getenv("TONE_MAX_CHUNKS", "3"))        # 테스트용 상한
HYP_PER_POLARITY = int(os.getenv("TONE_HYP_PER_POLARITY", "1"))  # 1~3
MAX_BODY_CHARS = 4000           # 학습 파이프라인과 동일해야 하는 값
BATCH_SIZE = int(os.getenv("TONE_BATCH_SIZE", "16"))

# 집계·라벨 판정 상수. 학습되지 않는 값이며 바꿔도 재학습이 필요 없다.
TOPK = 2
MIXED_THRESHOLD = 0.50
NEUTRAL_THRESHOLD = 0.40

# --- field_id → 분야 -------------------------------------------------------
# theme_catalog.json의 field_id 체계는 5종이고 CULTURE가 없다.
# 문화·종교(theme 38)와 관광(37)은 field 3(사회) 아래에 들어가 있다.
# 학습 파이프라인은 CULTURE를 별도 분야로 두므로 theme 단위로 예외 처리한다.
FIELD_ID_TO_CATEGORY: dict[int, str] = {
    1: "POLITICS",
    2: "ECONOMY",
    3: "SOCIETY",
    4: "TECH",
    5: "SPORTS",
}
CULTURE_THEME_IDS = {37, 38}
DEFAULT_CATEGORY = "SOCIETY"


def resolve_category(field_id: Any, theme_id: Any = None) -> str:
    """worker의 (field_id, theme_id)를 학습 파이프라인의 분야 6종으로 변환한다."""
    try:
        theme = int(theme_id) if theme_id is not None else None
    except (TypeError, ValueError):
        theme = None
    if theme in CULTURE_THEME_IDS:
        return "CULTURE"
    try:
        return FIELD_ID_TO_CATEGORY.get(int(field_id), DEFAULT_CATEGORY)
    except (TypeError, ValueError):
        return DEFAULT_CATEGORY


# --- 가설 문장 -------------------------------------------------------------
# 학습 파이프라인(distill/hypotheses.py)과 동일한 문구여야 한다.
# 극성당 3개가 원본이고, 앞에서부터 HYP_PER_POLARITY개만 사용한다.
# ECONOMY/TECH 부정 가설에 risk 계열 어휘를 넣지 말 것. 중립 기사가 과반응해
# 부정 축의 기저율이 올라간다.
TONE_HYPOTHESES: dict[str, dict[str, list[str]]] = {
    "POLITICS": {
        "pos": [
            "This text describes a political development in favorable or approving terms.",
            "This text reports cooperation, agreement or successful governance.",
            "This text presents the political actors or their decisions in a positive light.",
        ],
        "neg": [
            "This text describes a political development in critical or disapproving terms.",
            "This text reports conflict, scandal, corruption or failure of governance.",
            "This text presents the political actors or their decisions in a negative light.",
        ],
    },
    "ECONOMY": {
        "pos": [
            "This text describes an economic development as favorable or improving.",
            "This text reports growth, recovery, profit or rising demand.",
            "This text presents the economic outlook optimistically.",
        ],
        "neg": [
            "This text describes an economic development as unfavorable or worsening.",
            "This text reports losses, recession, layoffs or falling demand.",
            "This text presents the economic outlook pessimistically.",
        ],
    },
    "SOCIETY": {
        "pos": [
            "This text describes a social development in a hopeful or constructive way.",
            "This text reports rescue, recovery, relief or an improvement in people's lives.",
            "This text presents the situation as resolved or improving.",
        ],
        "neg": [
            "This text describes a social development in a distressing or alarming way.",
            "This text reports a crime, accident, death, illness or worsening hardship.",
            "This text presents the situation as harmful or deteriorating.",
        ],
    },
    "TECH": {
        "pos": [
            "This text describes a technological development as promising or beneficial.",
            "This text reports a breakthrough, successful launch or improved performance.",
            "This text presents the technology or its makers favorably.",
        ],
        "neg": [
            "This text describes a technological development as troubled or harmful.",
            "This text reports a failure, defect, breach, outage or abandoned project.",
            "This text presents the technology or its makers unfavorably.",
        ],
    },
    "CULTURE": {
        "pos": [
            "This text describes a cultural work or figure approvingly.",
            "This text reports acclaim, an award, popularity or a successful release.",
            "This text presents the artist or work in a flattering light.",
        ],
        "neg": [
            "This text describes a cultural work or figure disapprovingly.",
            "This text reports criticism, controversy, poor reception or a cancellation.",
            "This text presents the artist or work in an unflattering light.",
        ],
    },
    "SPORTS": {
        "pos": [
            "This text describes a sporting outcome favorably for the subject of the article.",
            "This text reports a victory, record, strong performance or return from injury.",
            "This text presents the athlete or team in a positive light.",
        ],
        "neg": [
            "This text describes a sporting outcome unfavorably for the subject of the article.",
            "This text reports a defeat, injury, poor performance, suspension or dispute.",
            "This text presents the athlete or team in a negative light.",
        ],
    },
}

# --- 텍스트 처리 -----------------------------------------------------------
# 학습 파이프라인(distill/text.py)의 규칙과 동일하게 유지해야 한다.
# ^ 앵커와 re.M 은 성능상 필수다. 없으면 greedy [^\n]* 가 모든 오프셋에서 줄
# 전체를 재스캔해 긴 기사 1건에 2초까지 걸린다.
_BOILERPLATE = [
    re.compile(
        r"^[^\n]*(?:무단\s*전재|재배포\s*금지|저작권자|All\s+rights\s+reserved"
        r"|転載を禁じ|無断転載|Alle\s+Rechte\s+vorbehalten)[^\n]*",
        re.I | re.M,
    ),
    re.compile(
        r"^[^\n]*(?:구독하기|뉴스레터\s*구독|관련\s*기사|Sign\s+up\s+for"
        r"|Follow\s+us\s+on|Read\s+more:|メルマガ登録|Newsletter\s+abonnieren)[^\n]*",
        re.I | re.M,
    ),
    re.compile(
        r"^[^\n]*(?:쿠키|cookie\s+settings|광고\s*차단|adblock"
        r"|Datenschutzerkl|Cookie-Einstellungen)[^\n]*",
        re.I | re.M,
    ),
]
_WS = re.compile(r"[ \t\u3000]+")
_BLANK = re.compile(r"\n{3,}")
_SENT = re.compile(r"[^\n]*?(?:[。．！？]+|[!?]+|(?<![A-Z])\.(?=\s|$)|$)")
# 제목 끝의 매체명 꼬리. teacher premise가 제목+본문이라 제거해야 한다.
_TITLE_TAIL = re.compile(
    r"\s*[\|｜]\s*[^\|｜]{1,40}$|\s*[｜|]\s*[^｜|]{1,40}\s*$"
)


def clean_text(text: str | None, drop_boilerplate: bool = True) -> str:
    """상용구를 제거하고 공백을 정규화한다."""
    if not text:
        return ""
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    t = t.replace("\u200b", "").replace("\xa0", " ")
    if drop_boilerplate:
        for pat in _BOILERPLATE:
            # 빈 문자열이 아니라 개행으로 치환해야 앞뒤 줄이 붙지 않는다.
            t = pat.sub("\n", t)
    t = "\n".join(_WS.sub(" ", ln).strip() for ln in t.split("\n"))
    return _BLANK.sub("\n\n", t).strip()


def strip_title_tail(title: str | None) -> str:
    """제목 끝에 붙은 매체명을 제거한다. 예: '... | 岩手日報ONLINE'."""
    t = clean_text(title, drop_boilerplate=False)
    if not t:
        return ""
    stripped = _TITLE_TAIL.sub("", t).strip()
    # 꼬리를 떼서 너무 짧아지면 원본을 쓴다(제목 본문에 구분자가 있는 경우).
    return stripped if len(stripped) >= max(8, len(t) // 3) else t


def split_sentences(text: str) -> list[str]:
    out: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        for m in _SENT.finditer(line):
            s = m.group().strip()
            if s:
                out.append(s)
    return out


class ToneScorer:
    """teacher NLI 모델로 기사 논조를 채점한다. 프로세스당 1회 로드."""

    def __init__(self, source: str | None = None, local_only: bool | None = None) -> None:
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        if source is None:
            source, resolved_local = resolve_model_source()
            local_only = resolved_local if local_only is None else local_only
        local_only = bool(local_only)

        self._torch = torch
        self.source = source
        # 리포트용 이름. 로컬 디렉터리면 그 이름을 쓴다.
        self.model_name = Path(source).name if local_only else source
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        if self.device == "cpu":
            logger.warning("Tone model runs on CPU; expect slow inference")

        self.tokenizer = AutoTokenizer.from_pretrained(
            source, local_files_only=local_only
        )
        self.model = AutoModelForSequenceClassification.from_pretrained(
            source, local_files_only=local_only
        )
        self.model.to(self.device).eval()

        # NLI 라벨 인덱스는 모델마다 순서가 다르다. 하드코딩하면 모델을 바꾸는
        # 순간 0.980이 0.020으로 조용히 뒤집힌다. config에서 찾아야 한다.
        id2label = {int(k): str(v).lower() for k, v in self.model.config.id2label.items()}
        try:
            self.entail_idx = next(i for i, v in id2label.items() if "entail" in v)
            self.contra_idx = next(i for i, v in id2label.items() if "contra" in v)
        except StopIteration as exc:
            raise RuntimeError(
                f"{source} is not an NLI model: id2label={id2label}"
            ) from exc
        logger.info(
            "Tone model loaded: source=%s local_only=%s device=%s "
            "entail=%d contradiction=%d",
            source, local_only, self.device, self.entail_idx, self.contra_idx,
        )

    # --- 내부 -------------------------------------------------------------
    def _n_tokens(self, text: str) -> int:
        return len(self.tokenizer.encode(text, add_special_tokens=False))

    def _chunk(self, text: str) -> list[str]:
        """문장 경계를 지키며 CHUNK_TOKENS 예산으로 그리디 패킹한다."""
        pieces: list[str] = []
        buf: list[str] = []
        buf_n = 0
        for sent in split_sentences(text):
            k = self._n_tokens(sent)
            if k > CHUNK_TOKENS:
                if buf:
                    pieces.append(" ".join(buf))
                    buf, buf_n = [], 0
                ids = self.tokenizer.encode(sent, add_special_tokens=False)
                for i in range(0, len(ids), CHUNK_TOKENS):
                    pieces.append(
                        self.tokenizer.decode(
                            ids[i:i + CHUNK_TOKENS], skip_special_tokens=True
                        )
                    )
                continue
            if buf_n + k > CHUNK_TOKENS and buf:
                pieces.append(" ".join(buf))
                buf, buf_n = [], 0
            buf.append(sent)
            buf_n += k
        if buf:
            pieces.append(" ".join(buf))
        # 짧은 꼬리 청크는 직전에 흡수한다. 3토큰짜리 조각은 확률이 극단으로
        # 튀고, topk 집계가 하필 그 조각을 우선 선택한다.
        if len(pieces) >= 2 and self._n_tokens(pieces[-1]) < MIN_CHUNK_TOKENS:
            pieces[-2] = pieces[-2] + " " + pieces[-1]
            pieces.pop()
        return pieces[:MAX_CHUNKS]

    def _entail_probs(self, premises: list[str], hypotheses: list[str]) -> np.ndarray:
        """(premise, hypothesis) 쌍마다 2-way softmax 후 entailment 확률."""
        torch = self._torch
        out: list[np.ndarray] = []
        with torch.no_grad():
            for i in range(0, len(premises), BATCH_SIZE):
                enc = self.tokenizer(
                    premises[i:i + BATCH_SIZE],
                    hypotheses[i:i + BATCH_SIZE],
                    truncation="only_first",   # 가설은 자르지 않는다
                    max_length=MODEL_MAX_TOKENS,
                    padding=True,
                    return_tensors="pt",
                ).to(self.device)
                logits = self.model(**enc).logits.float().cpu().numpy()
                out.append(logits)
        if not out:
            return np.zeros(0, dtype=np.float64)
        logits = np.concatenate(out, axis=0)
        # neutral을 버리고 entail vs contradiction 2-way softmax.
        # neutral을 남기면 "모르겠다"가 확률 질량을 갉아먹어 신호가 뭉개지고,
        # 긍정 가설과 부정 가설이 경쟁하지 않아야 mixed가 표현된다.
        pair = logits[:, [self.contra_idx, self.entail_idx]].astype(np.float64)
        pair -= pair.max(axis=1, keepdims=True)
        e = np.exp(pair)
        return e[:, 1] / e.sum(axis=1)

    def _chunk_probs(
        self, chunks: list[str], category: str
    ) -> tuple[np.ndarray, np.ndarray]:
        """청크별 (p_pos, p_neg). student로 교체할 때 이 메서드만 바꾸면 된다."""
        hyp = TONE_HYPOTHESES.get(category, TONE_HYPOTHESES[DEFAULT_CATEGORY])
        pos = hyp["pos"][:HYP_PER_POLARITY]
        neg = hyp["neg"][:HYP_PER_POLARITY]
        flat = pos + neg
        premises = [c for c in chunks for _ in flat]
        hypotheses = [h for _ in chunks for h in flat]
        p = self._entail_probs(premises, hypotheses).reshape(len(chunks), len(flat))
        n = len(pos)
        return p[:, :n].mean(axis=1), p[:, n:].mean(axis=1)

    # --- 외부 -------------------------------------------------------------
    def score(self, title: str | None, body: str | None, category: str) -> dict[str, Any]:
        text = "\n\n".join(
            x for x in (strip_title_tail(title), clean_text(body)[:MAX_BODY_CHARS]) if x
        )
        chunks = self._chunk(text)
        if not chunks:
            return make_sentiment(0.0, 0.0, model="empty", category=category, n_chunks=0)
        p_pos, p_neg = self._chunk_probs(chunks, category)
        a, b = agg_topk_mean(p_pos, p_neg, TOPK)
        return make_sentiment(
            a, b, model=self.model_name, category=category, n_chunks=len(chunks)
        )


# --- 집계·라벨 판정 (순수 함수, 모델 없이 테스트 가능) ----------------------
def agg_topk_mean(
    p_pos: np.ndarray, p_neg: np.ndarray, topk: int = TOPK
) -> tuple[float, float]:
    """극성차가 큰 상위 k개 청크만 평균한다.

    길이 가중평균을 쓰지 않는 이유: 부정 가설은 중립 텍스트에도 조금 더 잘
    걸린다. 중립 청크가 여러 개 붙으면 그 편향이 누적되어 명백한 긍정 기사가
    neutral로 밀린다. 극성차 기준으로 고르면 중립 청크는 몇 개가 붙어도
    선택되지 않는다.
    """
    a = np.asarray(p_pos, dtype=np.float64).ravel()
    b = np.asarray(p_neg, dtype=np.float64).ravel()
    if a.size == 0:
        return 0.0, 0.0
    k = max(1, min(int(topk), a.size))
    diff = np.abs(a - b)
    # 동점 시 앞 청크 우선. argsort만 쓰면 실행마다 순서가 달라질 수 있다.
    order = np.lexsort((np.arange(a.size), -diff))[:k]
    return float(a[order].mean()), float(b[order].mean())


def decide_label(p_pos: float, p_neg: float) -> str:
    """mixed 검사가 먼저다. (0.7, 0.65)는 '큰 쪽' 규칙으로는 positive지만
    실제로는 호재와 악재가 공존하는 기사다."""
    if p_pos >= MIXED_THRESHOLD and p_neg >= MIXED_THRESHOLD:
        return "mixed"
    if p_pos < NEUTRAL_THRESHOLD and p_neg < NEUTRAL_THRESHOLD:
        return "neutral"
    return "positive" if p_pos >= p_neg else "negative"


def tone_point(p_pos: float, p_neg: float) -> float:
    """0~100. DB의 article.tone_score로 들어가는 값.

    주의: mixed(0.72, 0.69)와 neutral(0.33, 0.30)이 똑같이 51.5가 될 수 있다.
    점수만 저장하면 '논조가 강하게 갈린 기사'와 '논조가 없는 기사'를 구분할
    수 없으므로 label을 함께 저장해야 한다.
    """
    return round(max(0.0, min(100.0, 50.0 * (1.0 + p_pos - p_neg))), 2)


def make_sentiment(
    p_pos: float,
    p_neg: float,
    *,
    model: str,
    category: str,
    n_chunks: int,
) -> dict[str, Any]:
    """Spark는 score만 읽는다(article_event._tone_score). 나머지는 진단용."""
    return {
        "score": tone_point(p_pos, p_neg),
        "label": decide_label(p_pos, p_neg),
        "confidence": round(float(max(p_pos, p_neg)), 4),
        "p_pos": round(float(p_pos), 4),
        "p_neg": round(float(p_neg), 4),
        "category": category,
        "n_chunks": n_chunks,
        "model": model,
    }


# --- singleton -------------------------------------------------------------
_scorer: ToneScorer | None = None
_load_failed = False


def get_tone_scorer() -> ToneScorer | None:
    """ToneScorer singleton. 로드 실패 시 None을 돌려주고 재시도하지 않는다."""
    global _scorer, _load_failed
    if _scorer is None and not _load_failed:
        try:
            _scorer = ToneScorer()
        except Exception:
            _load_failed = True
            logger.exception("Tone model load failed; falling back to dummy score 50.0")
    return _scorer


def score_article(
    article: dict[str, Any], field_id: Any = None, theme_id: Any = None
) -> dict[str, Any]:
    """main 파이프라인에서 호출하는 래퍼."""
    category = resolve_category(field_id, theme_id)
    if not TONE_ENABLED:
        return make_sentiment(0.0, 0.0, model="disabled", category=category, n_chunks=0)
    scorer = get_tone_scorer()
    if scorer is None:
        return make_sentiment(0.0, 0.0, model="dummy", category=category, n_chunks=0)
    try:
        return scorer.score(article.get("title"), article.get("body"), category)
    except Exception:
        # 기사 1건의 추론 실패로 배치 전체를 죽이지 않는다.
        logger.exception(
            "Tone scoring failed for article_id=%s", article.get("article_id")
        )
        return make_sentiment(0.0, 0.0, model="error", category=category, n_chunks=0)
