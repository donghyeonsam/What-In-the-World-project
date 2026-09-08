"""Spark Structured Streaming: news.enriched.v1 -> news.event.v1."""

from __future__ import annotations

import os

from article_event import transform_kafka_message
from pyspark.sql import SparkSession
from pyspark.sql.types import StringType, StructField, StructType


# Compose와 운영 환경에서 바꿀 수 있도록 모든 연결 정보는 환경 변수로 받는다.
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
KAFKA_ENRICHED_TOPIC = os.getenv("KAFKA_ENRICHED_TOPIC", "news.enriched.v1")
KAFKA_EVENT_TOPIC = os.getenv("KAFKA_EVENT_TOPIC", "news.event.v1")
SPARK_CHECKPOINT_LOCATION = os.getenv(
    "SPARK_CHECKPOINT_LOCATION",
    "hdfs://namenode:9000/checkpoints/enriched-article-events-v1",
)
SPARK_STARTING_OFFSETS = os.getenv("SPARK_STARTING_OFFSETS", "earliest")


# Spark Kafka Sink가 요구하는 key/value 컬럼의 스키마다.
OUTPUT_SCHEMA = StructType(
    [
        StructField("key", StringType(), nullable=False),
        StructField("value", StringType(), nullable=False),
    ]
)


def _transform_partition(rows):
    # 한 레코드마다 Python Worker를 호출하지 않고 Partition 단위로 변환 함수를
    # 실행해 Python/JVM 호출 횟수를 줄인다.
    for row in rows:
        yield transform_kafka_message(row.value)


def write_event_batch(batch_df, batch_id: int) -> None:
    """Transform and publish one micro-batch to Kafka."""

    spark = batch_df.sparkSession

    # Kafka Source의 value는 binary이므로 문자열로 변환한 뒤, 각 Partition에서
    # Enriched Article을 ARTICLE_UPSERT key/value 쌍으로 변환한다.
    output_rows = batch_df.selectExpr("CAST(value AS STRING) AS value").rdd.mapPartitions(
        _transform_partition
    )

    output_df = spark.createDataFrame(output_rows, schema=OUTPUT_SCHEMA)

    # topic 옵션을 지정했기 때문에 각 Row에는 key와 value만 있으면 된다.
    (
        output_df.write.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
        .option("topic", KAFKA_EVENT_TOPIC)
        .save()
    )
    print(f"Published Spark batch {batch_id} to {KAFKA_EVENT_TOPIC}")


def main() -> None:
    # Driver가 Spark Standalone Cluster에 제출하는 Structured Streaming 앱이다.
    spark = SparkSession.builder.appName("news-enriched-article-events-v1").getOrCreate()
    spark.sparkContext.setLogLevel(os.getenv("SPARK_LOG_LEVEL", "WARN"))

    # news.enriched.v1을 지속적으로 읽는다. startingOffsets는 체크포인트가 처음
    # 생성될 때만 적용되고, 재시작 후에는 체크포인트에 저장된 offset부터 이어간다.
    enriched_stream = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
        .option("subscribe", KAFKA_ENRICHED_TOPIC)
        .option("startingOffsets", SPARK_STARTING_OFFSETS)
        .option("failOnDataLoss", "true")
        .load()
    )

    # foreachBatch를 사용해 Spark Micro Batch마다 검증/변환 후 Kafka에 발행한다.
    # 체크포인트는 HDFS에 저장해 Driver 컨테이너가 재생성되어도 진행 위치를 보존한다.
    query = (
        enriched_stream.writeStream.foreachBatch(write_event_batch)
        .option("checkpointLocation", SPARK_CHECKPOINT_LOCATION)
        .queryName("news-enriched-article-events-v1")
        .start()
    )
    query.awaitTermination()


if __name__ == "__main__":
    main()
