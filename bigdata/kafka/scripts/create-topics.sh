#!/usr/bin/env bash
set -euo pipefail

KAFKA_CONTAINER="${KAFKA_CONTAINER:-news-kafka}"
BOOTSTRAP_SERVER="${KAFKA_BOOTSTRAP_SERVER:-kafka:29092}"
KAFKA_TOPICS="${KAFKA_TOPICS_COMMAND:-/opt/kafka/bin/kafka-topics.sh}"

run_kafka_topics() {
  if [ -x "$KAFKA_TOPICS" ]; then
    "$KAFKA_TOPICS" "$@"
  else
    docker exec "$KAFKA_CONTAINER" "$KAFKA_TOPICS" "$@"
  fi
}

echo "Waiting for Kafka..."

for attempt in $(seq 1 30); do
  if run_kafka_topics \
    --bootstrap-server "$BOOTSTRAP_SERVER" \
    --list >/dev/null 2>&1; then
    break
  fi

  if [ "$attempt" -eq 30 ]; then
    echo "Kafka did not become ready within 60 seconds." >&2
    exit 1
  fi

  sleep 2
done

create_topic() {
  local topic_name="$1"
  local partitions="$2"

  run_kafka_topics \
    --bootstrap-server "$BOOTSTRAP_SERVER" \
    --create \
    --if-not-exists \
    --topic "$topic_name" \
    --partitions "$partitions" \
    --replication-factor 1
}

create_topic "news.raw.v1" 6
create_topic "news.enriched.v1" 6
create_topic "news.unclassified.v1" 6
create_topic "news.event.v1" 3

echo "Kafka topics:"
run_kafka_topics \
  --bootstrap-server "$BOOTSTRAP_SERVER" \
  --list

