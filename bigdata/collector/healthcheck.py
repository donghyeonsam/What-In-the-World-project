#!/usr/bin/env python3

import json
import os
import sys
import time
from pathlib import Path


def fail(message):
    print(message, file=sys.stderr)
    raise SystemExit(1)


health_file = Path(
    os.getenv("COLLECTOR_HEALTH_FILE", "/data/collector/collector.heartbeat")
)
max_age_seconds = int(os.getenv("COLLECTOR_HEALTH_MAX_AGE_SECONDS", "900"))

try:
    age_seconds = time.time() - health_file.stat().st_mtime
except FileNotFoundError:
    fail(f"collector heartbeat is missing: {health_file}")

if age_seconds > max_age_seconds:
    fail(
        f"collector heartbeat is stale: {age_seconds:.0f}s "
        f"(limit: {max_age_seconds}s)"
    )

try:
    collection_mode = json.loads(health_file.read_text(encoding="utf-8") or "{}").get("collection_mode")
except (ValueError, AttributeError):
    collection_mode = None
if collection_mode == "observe":
    print("Collector observation heartbeat is fresh; Kafka is disabled.")
    raise SystemExit(0)

from confluent_kafka.admin import AdminClient

bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
topic = os.getenv("KAFKA_RAW_TOPIC", "news.raw.v1")

try:
    metadata = AdminClient(
        {
            "bootstrap.servers": bootstrap_servers,
            "client.id": "news-collector-healthcheck",
        }
    ).list_topics(topic=topic, timeout=5)
except Exception as exc:
    fail(f"Kafka metadata request failed: {type(exc).__name__}: {exc}")

topic_metadata = metadata.topics.get(topic)
if topic_metadata is None:
    fail(f"Kafka topic is missing: {topic}")
if topic_metadata.error is not None:
    fail(f"Kafka topic is unavailable: {topic_metadata.error}")
