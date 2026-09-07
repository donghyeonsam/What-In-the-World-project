"""
Kafka Producer 모듈.

NLP 처리가 완료된 뉴스 데이터를
news.enriched.v1 토픽으로 전송한다.
"""

import json

from confluent_kafka import Producer

from config import (
    KAFKA_BOOTSTRAP_SERVERS,
    KAFKA_ENRICHED_TOPIC,
)


def create_producer():
    """
    NLP Worker에서 사용할 Kafka Producer를 생성한다.
    """
    producer = Producer(
        {
            "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,

            # Producer를 식별하기 위한 이름
            "client.id": "nlp-worker",

            # 모든 replica가 메시지를 확인한 뒤 성공 처리
            "acks": "all",

            # 동일 메시지 중복 전송 가능성을 줄이기 위한 설정
            "enable.idempotence": True,

            # 네트워크 전송량 절감을 위한 압축
            "compression.type": "snappy",
        }
    )

    return producer


def send_enriched_article(producer, article):
    """
    NLP 처리 결과가 포함된 기사 데이터를
    news.enriched.v1 토픽으로 전송한다.
    """

    article_id = article["article_id"]

    payload = json.dumps(
        article,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    producer.produce(
        topic=KAFKA_ENRICHED_TOPIC,
        key=article_id,
        value=payload,
    )


def flush_producer(producer):
    """
    Producer 내부에 대기 중인 메시지가
    Kafka에 모두 전달될 때까지 기다린다.
    """
    producer.flush()