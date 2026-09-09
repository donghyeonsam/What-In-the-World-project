"""Kafka 수신과 배치 완료 후 offset 저장. invalid JSON도 archive 단계로 전달한다."""
import json

from confluent_kafka import Consumer, KafkaError

from config import (
    KAFKA_BOOTSTRAP_SERVERS, KAFKA_RAW_TOPIC,
    KAFKA_CONSUMER_GROUP, NLP_BATCH_SIZE,
)


def create_consumer():
    if NLP_BATCH_SIZE <= 0:
        raise ValueError("NLP_BATCH_SIZE must be positive")
    consumer = Consumer({
        "bootstrap.servers": KAFKA_BOOTSTRAP_SERVERS,
        "group.id": KAFKA_CONSUMER_GROUP,
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })
    try:
        consumer.subscribe([KAFKA_RAW_TOPIC])
    except BaseException:
        consumer.close()
        raise
    return consumer


def _reject_constant(value):
    raise ValueError(f"Invalid JSON constant: {value}")


def consume_batch(consumer):
    batch = []
    while len(batch) < NLP_BATCH_SIZE:
        message = consumer.poll(timeout=1.0)
        if message is None:
            break
        if message.error():
            if message.error().code() == KafkaError._PARTITION_EOF:
                continue
            raise RuntimeError(f"Kafka consumer error: {message.error()}")

        item = {"message": message, "article": None}
        try:
            value = message.value()
            if value is None:
                raise ValueError("null Kafka payload")
            item["article"] = json.loads(
                value.decode("utf-8"), parse_constant=_reject_constant,
            )
            # Reject overflowed numbers and lone surrogates before archiving.
            json.dumps(item["article"], allow_nan=False, ensure_ascii=False).encode("utf-8")
        except (UnicodeError, ValueError, RecursionError) as exc:
            item["invalid_reason"] = f"Invalid Kafka JSON: {exc}"
        batch.append(item)
    return batch


def commit_batch(consumer):
    # 모든 유효 메시지의 delivery 완료 또는 명시적 invalid 폐기 후에만 호출한다.
    results = consumer.commit(asynchronous=False)
    failures = [result for result in (results or []) if result.error]
    if failures:
        raise RuntimeError(f"Kafka offset commit failed: {failures}")
