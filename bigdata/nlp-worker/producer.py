"""Kafka broker acknowledgement를 검증하는 단일 Worker producer."""
import json

from confluent_kafka import Producer
from config import KAFKA_BOOTSTRAP_SERVERS, KAFKA_ENRICHED_TOPIC


class DeliveryProducer:
    def __init__(self, client):
        self.client = client
        self.pending = 0
        self.errors = []

    def on_delivery(self, error, message):
        self.pending -= 1
        if error is not None:
            self.errors.append(str(error))


def create_producer():
    return DeliveryProducer(Producer({
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
        "client.id": "nlp-worker",
        "acks": "all",
        "enable.idempotence": True,
        "compression.type": "snappy",
    }))


def send_enriched_article(producer, article):
    payload = json.dumps(
        article, ensure_ascii=False, separators=(",", ":"), allow_nan=False,
    )
    producer.pending += 1
    try:
        producer.client.produce(
            topic=KAFKA_ENRICHED_TOPIC,
            key=article["article_id"],
            value=payload,
            on_delivery=producer.on_delivery,
        )
    except Exception:
        producer.pending -= 1
        raise
    producer.client.poll(0)
    if producer.errors:
        raise RuntimeError(f"Kafka delivery failed: {producer.errors}")


def flush_producer(producer):
    # timeout은 librdkafka 기본 message.timeout.ms(300000)와 같은 300초.
    # 애플리케이션 retry/backoff는 추가하지 않는다.
    remaining = producer.client.flush(300.0)
    if remaining or producer.pending:
        raise TimeoutError(
            f"Kafka delivery incomplete: queue={remaining}, pending={producer.pending}"
        )
    if producer.errors:
        raise RuntimeError(f"Kafka delivery failed: {producer.errors}")
