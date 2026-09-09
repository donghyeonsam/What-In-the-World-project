"""config.yaml 로더. 코드 어디에도 설정값을 하드코딩하지 않기 위한 유일한 진입점."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config.yaml"


class Config(dict):
    """점 접근이 되는 dict. cfg.teacher.batch_size 처럼 쓴다."""

    def __getattr__(self, key: str) -> Any:
        try:
            value = self[key]
        except KeyError:
            raise AttributeError(f"config.yaml에 '{key}' 항목이 없음") from None
        return Config(value) if isinstance(value, dict) else value

    def require(self, key: str) -> Any:
        """없으면 조용히 None이 되는 대신 즉시 죽는다.

        게이트 값이 오타로 None이 되면 게이트가 통째로 사라진 채
        파이프라인이 끝까지 돈다. 이 프로젝트에서 가장 위험한 종류의 버그다.
        """
        if key not in self:
            raise KeyError(f"config.yaml에 필수 항목 '{key}' 없음")
        return getattr(self, key)


def load_config(path: str | Path | None = None) -> Config:
    path = Path(path) if path else DEFAULT_CONFIG
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    cfg = Config(raw)
    cfg["_path"] = str(path)
    _validate(cfg)
    return cfg


def _validate(cfg: Config) -> None:
    cats = cfg.require("categories")
    if len(cats) != 6 or len(set(cats)) != 6:
        raise ValueError(f"categories는 중복 없는 6개여야 함: {cats}")
    st = cfg.require("student")
    if st["head_tokens"] + st["tail_tokens"] > st["max_length"]:
        raise ValueError("student.head_tokens + tail_tokens > max_length")
    agg = cfg.require("aggregate")
    if agg["method"] not in ("topk_mean", "weighted_mean", "max"):
        raise ValueError(f"알 수 없는 aggregate.method: {agg['method']}")
    if cfg.require("teacher")["max_length"] > 512:
        raise ValueError("teacher.max_length는 512를 넘을 수 없음 (모델 상한)")


def work_path(cfg: Config, *parts: str) -> Path:
    """work_dir 아래 경로. 부모 디렉터리까지 만들어서 돌려준다."""
    p = (ROOT / cfg.data["work_dir"]).joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def out_path(cfg: Config, *parts: str) -> Path:
    p = (ROOT / cfg.output["dir"]).joinpath(*parts)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def input_path(cfg: Config) -> Path:
    return (ROOT / cfg.data["input"]).resolve()
