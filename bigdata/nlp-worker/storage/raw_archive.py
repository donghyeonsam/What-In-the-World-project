"""
원본 뉴스 아카이브 저장 모듈.

Kafka의 news.raw.v1 토픽에서 읽어온 원본 기사 데이터를
nlp-worker/data/raw 디렉토리 아래 날짜별 JSONL 파일로 저장한다.
"""

import json
from datetime import datetime, timezone
from pathlib import Path


# nlp-worker/data/raw 디렉토리에 원본 기사 데이터를 저장한다.
RAW_DATA_DIR = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "raw"
)


# 현재 UTC 날짜를 기준으로 저장할 JSONL 파일 경로를 반환한다.
def get_archive_file_path():
    current_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return RAW_DATA_DIR / f"{current_date}.jsonl"


# Kafka에서 읽어온 기사 배치를 날짜별 JSONL 파일에 이어서 저장한다.
def archive_batch(batch):
    # data/raw 디렉토리가 없으면 자동으로 생성한다.
    RAW_DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    archive_file = get_archive_file_path()

    # append 모드로 열어 기존 데이터 뒤에 계속 추가한다.
    with archive_file.open(
            "a",
            encoding="utf-8",
    ) as file:

        for item in batch:
            article = item["article"]

            # 기사 하나를 JSON 한 줄로 저장한다.
            file.write(
                json.dumps(
                    article,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )

            # JSONL 형식을 위해 기사마다 줄바꿈한다.
            file.write("\n")