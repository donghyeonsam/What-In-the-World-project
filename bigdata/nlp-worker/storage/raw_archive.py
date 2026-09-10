"""원본 JSONL 보존. 저장 실패는 전파하며 재처리 시 중복 append를 허용한다."""
import base64
import json
import os
from datetime import datetime, timezone
from pathlib import Path

RAW_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def get_archive_file_path():
    return RAW_DATA_DIR / f"{datetime.now(timezone.utc):%Y-%m-%d}.jsonl"


def archive_batch(batch):
    if not batch:
        return
    # 직렬화는 파일을 열기 전에 완료해 직렬화 오류에 의한 부분 쓰기를 방지한다.
    lines = []
    for item in batch:
        if item.get("invalid_reason"):
            message = item["message"]
            raw = message.value()
            record = {
                "topic": message.topic(), "partition": message.partition(),
                "offset": message.offset(), "invalid_reason": item["invalid_reason"],
                "raw_value_base64": (
                    base64.b64encode(raw).decode("ascii") if raw is not None else None
                ),
            }
        else:
            record = item["article"]
        lines.append(json.dumps(record, ensure_ascii=False, separators=(",", ":"),
                               allow_nan=False) + "\n")
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with get_archive_file_path().open("a", encoding="utf-8") as file:
        file.write("".join(lines))
        file.flush()
        os.fsync(file.fileno())
