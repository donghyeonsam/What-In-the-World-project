"""기사 제목을 본문 문맥을 참고하여 자연스러운 한국어로 번역한다."""

import logging

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

logger = logging.getLogger(__name__)


MODEL_NAME = "Qwen/Qwen3-8B"

# 제목 번역의 문맥으로 사용할 본문 최대 문자 수
BODY_LEAD_MAX_CHARS = 1000

# 번역 결과가 제목이므로 과도한 생성을 방지
MAX_NEW_TOKENS = 128


_tokenizer = None
_model = None


def _load_model():
    """Qwen 모델을 최초 1회만 GPU에 로드한다."""
    global _tokenizer, _model

    if _tokenizer is not None and _model is not None:
        return _tokenizer, _model

    logger.info("Loading title translation model: %s", MODEL_NAME)

    _tokenizer = AutoTokenizer.from_pretrained(
        MODEL_NAME,
        trust_remote_code=True,
    )

    _model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
    )

    _model.to("cuda")
    _model.eval()

    logger.info(
        "Title translation model loaded: %s device=%s",
        MODEL_NAME,
        next(_model.parameters()).device,
    )

    return _tokenizer, _model


def _build_prompt(title, body_lead, language_code):
    return f"""
다음 해외 뉴스 기사의 제목을 한국어 뉴스 제목으로 번역하세요.

원문 언어: {language_code}

[원문 제목]
{title}

[본문 참고]
{body_lead}

번역 규칙:
1. 본문은 제목의 문맥을 파악하기 위한 참고 자료로만 사용하세요.
2. 제목에 없는 사실을 새롭게 추가하거나 추측하지 마세요.
3. 원문의 시간, 숫자, 인명, 지명, 기관명, 사건 관계를 정확하게 유지하세요.
4. "몇 시간 전", "며칠 후" 등 시간 표현을 임의로 바꾸지 마세요.
5. 직역투를 피하고 자연스러운 한국 언론 제목 형식으로 번역하세요.
6. 원문이 자극적인 표현을 사용하더라도 의미와 뉘앙스를 임의로 삭제하지 마세요.
7. 출력은 반드시 한국어로 작성하세요.
8. 중국어 한자나 일본어 문자를 사용하지 마세요.
9. 고유명사 등 필요한 경우에만 영문 알파벳과 숫자를 사용할 수 있습니다.
10. 설명, 주석, 따옴표 없이 번역된 제목 한 줄만 출력하세요.
""".strip()


def _clean_translation(text):
    """모델 출력에서 불필요한 공백이나 따옴표를 제거한다."""
    if not isinstance(text, str):
        return ""

    text = text.strip()

    # 모델이 가끔 제목 전체를 따옴표로 감싸는 경우 제거
    if len(text) >= 2:
        pairs = (
            ('"', '"'),
            ("'", "'"),
            ("“", "”"),
            ("‘", "’"),
        )

        for left, right in pairs:
            if text.startswith(left) and text.endswith(right):
                text = text[1:-1].strip()
                break

    return text


def translate_title(article, language_code):
    """
    기사 제목을 한국어로 번역한다.

    - 한국어 기사: 원문 제목 그대로 반환
    - 그 외 언어: 제목 + 본문 앞부분을 Qwen에 전달하여 번역
    """

    title = article["title"].strip()

    # 이미 한국어인 경우 LLM을 호출하지 않는다.
    if language_code == "ko":
        return title

    body = article.get("body") or ""
    body_lead = body.strip()[:BODY_LEAD_MAX_CHARS]

    tokenizer, model = _load_model()

    prompt = _build_prompt(
        title=title,
        body_lead=body_lead,
        language_code=language_code,
    )

    messages = [
        {
            "role": "user",
            "content": prompt,
        }
    ]

    text = tokenizer.apply_chat_template(
        messages,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )

    inputs = tokenizer(
        text,
        return_tensors="pt",
    ).to(model.device)

    with torch.inference_mode():
        outputs = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )

    # 입력 prompt 부분을 제외하고 새로 생성된 토큰만 decode
    generated_tokens = outputs[0][inputs["input_ids"].shape[1]:]

    translated_title = tokenizer.decode(
        generated_tokens,
        skip_special_tokens=True,
    )

    translated_title = _clean_translation(translated_title)

    if not translated_title:
        raise RuntimeError(
            f"Title translation returned empty result: article_id={article.get('article_id')}"
        )

    return translated_title