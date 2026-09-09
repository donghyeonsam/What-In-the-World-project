"""fastText 언어 판별. 최초 사용 시 1회 로딩하며 실패 시 원인을 보존한다."""
from pathlib import Path

MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "lid.176.bin"
_language_model = None


def get_language_model():
    global _language_model
    if _language_model is None:
        if not MODEL_PATH.is_file():
            raise FileNotFoundError(f"fastText language model missing: {MODEL_PATH}")
        import fasttext
        _language_model = fasttext.load_model(str(MODEL_PATH))
    return _language_model


def detect_language(article):
    text = " ".join(
        f"{article.get('title') or ''}\n{article.get('body') or ''}".split()
    )
    if not text:
        return None
    labels, _ = get_language_model().predict(text, k=1)
    if len(labels) == 0:
        return None
    return labels[0].removeprefix("__label__")
