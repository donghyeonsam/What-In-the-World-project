"""JSONL 스트리밍과 샤드 단위 재개. JupyterHub 24시간 제한 대응의 기반."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Iterator


def read_jsonl(path: str | Path, limit: int | None = None,
               skip: int = 0) -> Iterator[dict]:
    """깨진 줄은 건너뛴다. skip은 재개용 입력 오프셋."""
    with open(path, "r", encoding="utf-8") as f:
        yielded = 0
        for i, line in enumerate(f):
            if i < skip:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            yield row
            yielded += 1
            if limit is not None and yielded >= limit:
                return


def write_jsonl(path: str | Path, rows: Iterable[dict], mode: str = "w") -> int:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(path, mode, encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            n += 1
    return n


def count_jsonl(path: str | Path) -> int:
    with open(path, "r", encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def shard_path(directory: str | Path, stem: str, idx: int) -> Path:
    return Path(directory) / f"{stem}.{idx:05d}.jsonl"


def existing_shards(directory: str | Path, stem: str) -> list[Path]:
    d = Path(directory)
    if not d.exists():
        return []
    return sorted(d.glob(f"{stem}.[0-9]*.jsonl"))


def resume_state(directory: str | Path, stem: str) -> tuple[int, int]:
    """(다음에 쓸 샤드 번호, 이미 처리한 입력 행 수).

    전제: 입력 1행 = 출력 1행. 그래서 label.py는 게이트 탈락분도
    버리지 않고 gate_pass=false로 그대로 쓴다. 탈락률 실측과
    재개 산수를 동시에 얻는 방식.
    """
    shards = existing_shards(directory, stem)
    return len(shards), sum(count_jsonl(p) for p in shards)


def read_shards(directory: str | Path, stem: str) -> Iterator[dict]:
    for p in existing_shards(directory, stem):
        yield from read_jsonl(p)


def iter_batches(items: Iterable[Any], size: int) -> Iterator[list]:
    buf: list = []
    for x in items:
        buf.append(x)
        if len(buf) >= size:
            yield buf
            buf = []
    if buf:
        yield buf
