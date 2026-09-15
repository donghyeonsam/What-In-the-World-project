"""Spark Structured Streaming: news.enriched.v1 -> news.event.v1."""

from __future__ import annotations

import json
import os

from article_event import InvalidEnrichedArticle, transform_kafka_message
from issue_matching import (
    InvalidIssueEmbedding,
    IssueCandidate,
    build_issue_result,
    parse_issue_candidate,
)
from streaming_metrics import register_streaming_metrics
from pyspark import StorageLevel
from pyspark.sql import SparkSession
from pyspark.sql.types import (
    ArrayType,
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)


# Compose와 운영 환경에서 바꿀 수 있도록 모든 연결 정보는 환경 변수로 받는다.
KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
KAFKA_ENRICHED_TOPIC = os.getenv("KAFKA_ENRICHED_TOPIC", "news.enriched.v1")
KAFKA_EVENT_TOPIC = os.getenv("KAFKA_EVENT_TOPIC", "news.event.v1")
KAFKA_UNCLASSIFIED_TOPIC = os.getenv(
    "KAFKA_UNCLASSIFIED_TOPIC", "news.unclassified.v1"
)
POSTGRESQL_URL = os.getenv("POSTGRESQL_URL", "").strip()
POSTGRESQL_USER = os.getenv("POSTGRESQL_USER", "").strip()
POSTGRESQL_PASSWORD = os.getenv("POSTGRESQL_PASSWORD", "")
ISSUE_MATCH_THRESHOLD = float(os.getenv("ISSUE_MATCH_THRESHOLD", "0.85"))
SPARK_CHECKPOINT_LOCATION = os.getenv(
    "SPARK_CHECKPOINT_LOCATION",
    "hdfs://namenode:9000/checkpoints/enriched-article-events-v1",
)
SPARK_STARTING_OFFSETS = os.getenv("SPARK_STARTING_OFFSETS", "earliest")


# ARTICLE_UPSERT 발행과 이슈 매칭에서 함께 사용할 검증 완료 기사 스키마다.
ARTICLE_SCHEMA = StructType(
    [
        StructField("key", StringType(), nullable=False),
        StructField("value", StringType(), nullable=False),
        StructField("article_id", StringType(), nullable=False),
        StructField("theme_id", LongType(), nullable=False),
        StructField(
            "embedding",
            ArrayType(DoubleType(), containsNull=False),
            nullable=False,
        ),
        StructField("title", StringType(), nullable=False),
        StructField("published_at", StringType(), nullable=False),
        StructField("occurred_at", StringType(), nullable=False),
    ]
)

# Kafka Sink의 topic 컬럼을 사용해 매칭 성공과 실패를 한 번에 분기한다.
MATCH_OUTPUT_SCHEMA = StructType(
    [
        StructField("topic", StringType(), nullable=False),
        StructField("key", StringType(), nullable=False),
        StructField("value", StringType(), nullable=False),
    ]
)


def _transform_kafka_partition(rows):
    """Spark 파티션의 정상 기사만 다음 처리 단계로 전달한다."""

    for row in rows:
        try:
            key, value = transform_kafka_message(row.value)
        except InvalidEnrichedArticle as exc:
            # 입력 오류 한 건은 기록하고 건너뛰되, 다음 기사는 계속 처리한다.
            print(
                "입력 데이터가 잘못되었습니다. "
                f"topic={row.topic} partition={row.partition} offset={row.offset}: {exc}"
            )
            continue

        # key/value는 ARTICLE_UPSERT 발행에 사용하고 나머지 컬럼은 이슈 매칭에 사용한다.
        event = json.loads(value)
        payload = event["payload"]
        yield (
            key,
            value,
            payload["article_id"],
            payload["theme_id"],
            payload["embedding"],
            payload["original_title"],
            payload["published_at"],
            event["occurred_at"],
        )


def _load_issue_candidates(spark, theme_ids: list[int]) -> dict[int, list[IssueCandidate]]:

    if not theme_ids:
        return {}
    if not POSTGRESQL_URL or not POSTGRESQL_USER or not POSTGRESQL_PASSWORD:
        raise RuntimeError(
            "POSTGRESQL_URL, POSTGRESQL_USER and POSTGRESQL_PASSWORD are required"
        )

    # theme_id는 정수로 확인된 값만 사용하므로 IN 절을 안전하게 구성할 수 있다.
    theme_id_csv = ",".join(str(theme_id) for theme_id in sorted(set(theme_ids)))
    query = f"""
        SELECT id AS issue_id, theme_id, embedding
        FROM issue
        WHERE theme_id IN ({theme_id_csv})
          AND embedding IS NOT NULL
    """
    issue_rows = (
        spark.read.format("jdbc")
        .option("url", POSTGRESQL_URL)
        .option("query", query)
        .option("user", POSTGRESQL_USER)
        .option("password", POSTGRESQL_PASSWORD)
        .option("driver", "org.postgresql.Driver")
        .option("fetchsize", "1000")
        .load()
        .collect()
    )

    issues_by_theme: dict[int, list[IssueCandidate]] = {}
    invalid_count = 0
    for row in issue_rows:
        try:
            issue = parse_issue_candidate(row.asDict(recursive=True))
        except InvalidIssueEmbedding as exc:
            # 잘못된 기존 Issue 한 건 때문에 전체 기사 배치를 중단하지 않는다.
            invalid_count += 1
            print(f"Skipped invalid Issue row: {exc}")
            continue
        issues_by_theme.setdefault(issue.theme_id, []).append(issue)

    print(
        f"Loaded {len(issue_rows) - invalid_count} Issue candidates "
        f"for themes {sorted(set(theme_ids))}; skipped {invalid_count} invalid rows"
    )
    return issues_by_theme


def _match_partition(
    rows,
    issues_by_theme,
    threshold: float,
    event_topic: str,
    unclassified_topic: str,
):
    # Driver가 조회한 작은 Issue 후보 목록을 Broadcast로 각 Executor에 전달한다.
    for row in rows:
        article = {
            "article_id": row.article_id,
            "theme_id": row.theme_id,
            "embedding": row.embedding,
            "title": row.title,
            "published_at": row.published_at,
            "occurred_at": row.occurred_at,
        }
        yield build_issue_result(
            article,
            issues_by_theme.value.get(row.theme_id, ()),
            threshold,
            event_topic,
            unclassified_topic,
        )


def write_event_batch(batch_df, batch_id: int) -> None:

    spark = batch_df.sparkSession

    # Kafka Source의 value는 binary이므로 문자열로 변환한 뒤, 각 Partition에서
    # Enriched Article을 ARTICLE_UPSERT key/value 쌍으로 변환한다.
    # Spark 4.2.0의 SPARK-59451을 피하기 위해 InMemoryRelation을 만드는
    # DataFrame.cache() 대신 그 입력 RDD를 보관한다. 첫 Kafka write가 RDD의
    # 모든 파티션을 materialize한 뒤 이어지는 action들이 같은 결과를 재사용한다.
    article_rows = (
        batch_df.selectExpr(
            "topic",
            "partition",
            "offset",
            "CAST(value AS STRING) AS value",
        )
        .rdd.mapPartitions(_transform_kafka_partition)
        .persist(StorageLevel.MEMORY_AND_DISK)
    )

    issues_by_theme = None
    try:
        article_df = spark.createDataFrame(article_rows, schema=ARTICLE_SCHEMA)

        # topic 옵션을 지정했기 때문에 각 Row에는 key와 value만 있으면 된다.
        (
            article_df.select("key", "value").write.format("kafka")
            .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
            .option("topic", KAFKA_EVENT_TOPIC)
            .save()
        )

        # 현재 배치에 포함된 Theme만 조회하여 불필요한 Issue 전체 스캔을 피한다.
        theme_ids = [
            row.theme_id
            for row in article_df.select("theme_id").distinct().collect()
        ]
        issues_by_theme = spark.sparkContext.broadcast(
            _load_issue_candidates(spark, theme_ids)
        )
        match_rows = article_df.rdd.mapPartitions(
            lambda rows: _match_partition(
                rows,
                issues_by_theme,
                ISSUE_MATCH_THRESHOLD,
                KAFKA_EVENT_TOPIC,
                KAFKA_UNCLASSIFIED_TOPIC,
            )
        )
        match_output_df = spark.createDataFrame(match_rows, schema=MATCH_OUTPUT_SCHEMA)

        # topic 컬럼 값에 따라 성공은 news.event.v1, 실패는
        # news.unclassified.v1으로 Kafka Sink가 분기한다.
        (
            match_output_df.write.format("kafka")
            .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
            .save()
        )
    finally:
        if issues_by_theme is not None:
            issues_by_theme.destroy()
        article_rows.unpersist()


def main() -> None:
    # Driver가 Spark Standalone Cluster에 제출하는 Structured Streaming 앱이다.
    spark = SparkSession.builder.appName("news-enriched-article-events-v1").getOrCreate()
    spark.sparkContext.setLogLevel(os.getenv("SPARK_LOG_LEVEL", "WARN"))
    register_streaming_metrics(spark, "news-enriched-article-events-v1")

    if not 0.0 <= ISSUE_MATCH_THRESHOLD <= 1.0:
        raise ValueError("이슈매칭 THRESHOLD값은 0~1사이여야 합니다.")
    if not POSTGRESQL_URL or not POSTGRESQL_USER or not POSTGRESQL_PASSWORD:
        raise RuntimeError(
            "DB 접근 환경변수가 필요합니다."
        )

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
