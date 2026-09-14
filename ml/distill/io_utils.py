"""JSONL 읽기·쓰기, 샤드 단위 재시작."""
from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from pathlib import Path


def read_jsonl(path: Path) -> Iterator[dict]:
    with Path(path).open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue            # 깨진 줄은 조용히 건너뛴다


def write_jsonl(path: Path, rows: Iterable[dict]) -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


def count_lines(path: Path) -> int:
    with Path(path).open(encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def shard_path(dir_: Path, idx: int) -> Path:
    return Path(dir_) / f"shard_{idx:04d}.jsonl"


def iter_shards(rows: Iterable[dict], size: int) -> Iterator[tuple[int, list[dict]]]:
    """rows 를 size 개씩 묶어 (샤드 번호, 리스트) 로 낸다."""
    buf: list[dict] = []
    idx = 0
    for r in rows:
        buf.append(r)
        if len(buf) >= size:
            yield idx, buf
            buf, idx = [], idx + 1
    if buf:
        yield idx, buf


def read_all_shards(dir_: Path) -> Iterator[dict]:
    for p in sorted(Path(dir_).glob("shard_*.jsonl")):
        yield from read_jsonl(p)
