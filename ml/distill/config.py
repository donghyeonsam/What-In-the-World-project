"""config.yaml 을 읽어 점 표기로 접근할 수 있게 만든다.

    cfg = load_config()
    cfg.teacher.model          → "MoritzLaurer/..."
    cfg.data.country_to_lang   → dict (키에 공백이 있어 dict 로 남긴다)
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import yaml


def _to_ns(obj):
    """dict 를 SimpleNamespace 로 재귀 변환.

    키가 파이썬 식별자가 아닌 dict(예: "South Korea")는 그대로 dict 로 둔다.
    """
    if isinstance(obj, dict):
        if all(isinstance(k, str) and k.isidentifier() for k in obj):
            return SimpleNamespace(**{k: _to_ns(v) for k, v in obj.items()})
        return {k: _to_ns(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_to_ns(x) for x in obj]
    return obj


def load_config(path: str | Path = "config.yaml") -> SimpleNamespace:
    with Path(path).open(encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    cfg = _to_ns(raw)

    # 경로를 Path 로 바꿔 두면 이후 코드에서 / 연산이 편하다
    cfg.data.input = Path(cfg.data.input)
    cfg.data.work_dir = Path(cfg.data.work_dir)
    cfg.data.work_dir.mkdir(parents=True, exist_ok=True)
    return cfg


def work_path(cfg, *parts) -> Path:
    """work_dir 아래 경로. 상위 디렉터리를 만들어 준다."""
    p = cfg.data.work_dir.joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p
