"""
NLP Worker 공통 설정 모듈.

Kafka 연결 정보, 토픽 이름, Consumer Group,
배치 크기 등의 환경설정을 관리한다.
"""

import os

# Kafka 브로커 주소
KAFKA_BOOTSTRAP_SERVERS = os.getenv(
    "KAFKA_BOOTSTRAP_SERVERS",
    "localhost:19092",
)

# NLP worker가 원본 뉴스를 읽을 Kafka 토픽
KAFKA_RAW_TOPIC = os.getenv(
    "KAFKA_RAW_TOPIC",
    "news.raw.v1",
)

# NLP worker가 분석 결과를 전송할 Kafka 토픽
KAFKA_ENRICHED_TOPIC = os.getenv(
    "KAFKA_ENRICHED_TOPIC",
    "news.enriched.v1",
)

# NLP worker의 consumer group ID
KAFKA_CONSUMER_GROUP = os.getenv(
    "KAFKA_CONSUMER_GROUP",
    "nlp-worker-v1",
)

# 한 번의 추론에서 처리할 기사 개수 (batch size)
NLP_BATCH_SIZE = int(
    os.getenv("NLP_BATCH_SIZE", "32")
)