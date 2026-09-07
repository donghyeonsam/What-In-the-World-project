"""
Kafka Consumer 모듈.

news.raw.v1 토픽에서 원본 뉴스 메시지를 읽고,
NLP 처리를 위한 배치 단위로 데이터를 수집한다.
"""

import json

from confluent_kafka import Consumer, KafkaError

from config import ( # config 상수들 가져오기
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_RAW_TOPIC,
    KAFKA_CONSUMER_GROUP,
    NLP_BATCH_SIZE,
)


def create_consumer():
    """
    NLP Worker에서 사용할 Kafka Consumer를 생성한다.
    """
    consumer = Consumer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
            "group.id": KAFKA_CONSUMER_GROUP,

            # Consumer Group에 저장된 offset이 없을 경우
            # 가장 오래된 메시지부터 읽는다.
            "auto.offset.reset": "earliest",

            # NLP 처리와 Kafka 전송이 성공한 뒤
            # 직접 offset을 commit하기 위해 자동 commit을 비활성화한다.
            "enable.auto.commit": False,
        }
    )

    consumer.subscribe([KAFKA_RAW_TOPIC]) # 해당 consumer는 이 토픽을 구독한다.

    return consumer


def consume_batch(consumer):
    """
    Kafka에서 최대 NLP_BATCH_SIZE개의 메시지를 읽어
    하나의 배치로 반환한다.
    """
    batch = []

    while len(batch) < NLP_BATCH_SIZE:
        message = consumer.poll(timeout=1.0)

        # 현재 읽을 메시지가 없으면 지금까지 모인 배치를 반환한다.
        if message is None:
            break

        if message.error():
            if message.error().code() == KafkaError._PARTITION_EOF:
                continue

            raise RuntimeError(
                f"Kafka consumer error: {message.error()}"
            )

        try:
            article = json.loads(
                message.value().decode("utf-8")
            )
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError(
                f"Invalid Kafka message: {exc}"
            ) from exc

        batch.append(
            {
                "message": message,
                "article": article,
            }
        )

    return batch