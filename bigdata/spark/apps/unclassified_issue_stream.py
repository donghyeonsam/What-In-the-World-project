"""Spark stream: news.unclassified.v1 -> clustered issue events."""

from __future__ import annotations

import os

from gms_issue_generator import (
    GmsConfig,
    GmsIssueGenerationError,
    generate_issue,
)
from issue_clustering import (
    InvalidUnclassifiedArticle,
    UnclassifiedArticle,
    build_issue_events,
    cluster_articles,
    filter_cluster_articles,
    merge_generated_issue_candidates,
    parse_unclassified_message,
)
from streaming_metrics import register_streaming_metrics
from pyspark import StorageLevel
from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import (
    ArrayType,
    DoubleType,
    LongType,
    StringType,
    StructField,
    StructType,
)


KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "kafka:29092")
KAFKA_UNCLASSIFIED_TOPIC = os.getenv(
    "KAFKA_UNCLASSIFIED_TOPIC", "news.unclassified.v1"
)
KAFKA_EVENT_TOPIC = os.getenv("KAFKA_EVENT_TOPIC", "news.event.v1")
POSTGRESQL_URL = os.getenv("POSTGRESQL_URL", "").strip()
POSTGRESQL_USER = os.getenv("POSTGRESQL_USER", "").strip()
POSTGRESQL_PASSWORD = os.getenv("POSTGRESQL_PASSWORD", "")

# MVP에서 모든 환경이 동일한 이슈 형성 기준을 사용하도록 코드 상수로 고정한다.
ISSUE_CLUSTER_TRIGGER_COUNT = 50
ISSUE_CLUSTER_MIN_SIZE = 4
ISSUE_CLUSTER_MIN_SAMPLES = 4
ISSUE_CLUSTER_MIN_MEMBER_CONFIDENCE = 0.80
ISSUE_CLUSTER_MIN_CENTROID_SIMILARITY = 0.92
ISSUE_CLUSTER_WINDOW_HOURS = 72
ISSUE_CLUSTER_REPRESENTATIVE_COUNT = 4
ISSUE_CLUSTER_MAX_ARTICLES_PER_THEME = int(
    os.getenv("ISSUE_CLUSTER_MAX_ARTICLES_PER_THEME", "2000")
)
GMS_BASE_URL = "https://gms.ssafy.io/gmsapi/api.openai.com/v1"
GMS_MODEL = os.getenv("GMS_MODEL", "gemini-2.5-flash-lite")
GMS_TIMEOUT_SECONDS = 30.0
GMS_MAX_ATTEMPTS = 3
GMS_CONFIG = GmsConfig(
    api_key=os.getenv("GMS_API_KEY", ""),
    base_url=GMS_BASE_URL,
    model=GMS_MODEL,
    timeout_seconds=GMS_TIMEOUT_SECONDS,
    max_attempts=GMS_MAX_ATTEMPTS,
)

SPARK_CHECKPOINT_LOCATION = os.getenv(
    "ISSUE_CLUSTER_CHECKPOINT_LOCATION",
    "hdfs://namenode:9000/checkpoints/unclassified-issue-stream-v1",
)
PENDING_STATE_LOCATION = os.getenv(
    "ISSUE_CLUSTER_STATE_LOCATION",
    "hdfs://namenode:9000/checkpoints/unclassified-issue-state-v1",
)
SPARK_STARTING_OFFSETS = os.getenv("ISSUE_CLUSTER_STARTING_OFFSETS", "earliest")


PENDING_SCHEMA = StructType(
    [
        StructField("article_id", StringType(), nullable=False),
        StructField("theme_id", LongType(), nullable=False),
        StructField(
            "embedding", ArrayType(DoubleType(), containsNull=False), nullable=False
        ),
        StructField("title", StringType(), nullable=False),
        StructField("summary", StringType(), nullable=True),
        StructField("published_at", StringType(), nullable=False),
        StructField("unclassified_at", StringType(), nullable=False),
    ]
)

EVENT_SCHEMA = StructType(
    [
        StructField("key", StringType(), nullable=False),
        StructField("value", StringType(), nullable=False),
    ]
)


def _parse_partition(rows):
    for row in rows:
        try:
            article = parse_unclassified_message(row.value)
            kafka_key = row.key.strip() if row.key is not None else None
            if kafka_key is not None and kafka_key != str(article.theme_id):
                raise InvalidUnclassifiedArticle(
                    "Kafka key must equal the message theme_id"
                )
        except InvalidUnclassifiedArticle as exc:
            print(
                "Skipped invalid unclassified article. "
                f"partition={row.partition} offset={row.offset}: {exc}"
            )
            continue
        yield (
            article.article_id,
            article.theme_id,
            list(article.embedding),
            article.title,
            article.summary,
            article.published_at,
            article.unclassified_at,
        )


def _path_exists(spark: SparkSession, path: str) -> bool:
    hadoop_path = spark._jvm.org.apache.hadoop.fs.Path(path)
    file_system = hadoop_path.getFileSystem(spark._jsc.hadoopConfiguration())
    return file_system.exists(hadoop_path)


def _read_pending_state(spark: SparkSession):
    # If the previous process stopped between the two atomic renames, recover
    # the last complete snapshot before reading Kafka's retried micro-batch.
    hadoop_path = spark._jvm.org.apache.hadoop.fs.Path(PENDING_STATE_LOCATION)
    backup_path = spark._jvm.org.apache.hadoop.fs.Path(
        f"{PENDING_STATE_LOCATION}.__backup"
    )
    file_system = hadoop_path.getFileSystem(spark._jsc.hadoopConfiguration())
    if not file_system.exists(hadoop_path) and file_system.exists(backup_path):
        if not file_system.rename(backup_path, hadoop_path):
            raise RuntimeError("Could not recover the pending issue state")
    if not _path_exists(spark, PENDING_STATE_LOCATION):
        return spark.createDataFrame([], schema=PENDING_SCHEMA)
    return spark.read.schema(PENDING_SCHEMA).parquet(PENDING_STATE_LOCATION)


def _write_pending_state(spark: SparkSession, remaining, batch_id: int) -> None:
    final_path = spark._jvm.org.apache.hadoop.fs.Path(PENDING_STATE_LOCATION)
    temporary_path = spark._jvm.org.apache.hadoop.fs.Path(
        f"{PENDING_STATE_LOCATION}.__tmp_{batch_id}"
    )
    backup_path = spark._jvm.org.apache.hadoop.fs.Path(
        f"{PENDING_STATE_LOCATION}.__backup"
    )
    file_system = final_path.getFileSystem(spark._jsc.hadoopConfiguration())

    if file_system.exists(temporary_path):
        file_system.delete(temporary_path, True)
    remaining.coalesce(1).write.mode("overwrite").parquet(temporary_path.toString())

    if file_system.exists(backup_path):
        file_system.delete(backup_path, True)
    had_previous_state = file_system.exists(final_path)
    if had_previous_state and not file_system.rename(final_path, backup_path):
        raise RuntimeError("Could not back up the pending issue state")
    if not file_system.rename(temporary_path, final_path):
        if had_previous_state and file_system.exists(backup_path):
            file_system.rename(backup_path, final_path)
        raise RuntimeError("Could not publish the pending issue state")
    if file_system.exists(backup_path):
        file_system.delete(backup_path, True)


def _jdbc_query(spark: SparkSession, query: str):
    return (
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


def _load_theme_names(
    spark: SparkSession, theme_ids: list[int]
) -> dict[int, str]:
    if not theme_ids:
        return {}
    theme_id_csv = ",".join(str(value) for value in sorted(set(theme_ids)))
    theme_rows = _jdbc_query(
        spark,
        f"SELECT id AS theme_id, name AS theme_name FROM theme WHERE id IN ({theme_id_csv})",
    )
    return {row.theme_id: row.theme_name for row in theme_rows}


def _to_article(row) -> UnclassifiedArticle:
    return UnclassifiedArticle(
        article_id=row.article_id,
        theme_id=row.theme_id,
        embedding=tuple(row.embedding),
        title=row.title,
        summary=row.summary,
        published_at=row.published_at,
        unclassified_at=row.unclassified_at,
    )


def write_cluster_batch(batch_df, batch_id: int) -> None:
    spark = batch_df.sparkSession
    parsed_rows = batch_df.selectExpr(
        "CAST(key AS STRING) AS key",
        "CAST(value AS STRING) AS value",
        "partition",
        "offset",
    ).rdd.mapPartitions(_parse_partition).persist(StorageLevel.MEMORY_AND_DISK)
    incoming = spark.createDataFrame(parsed_rows, schema=PENDING_SCHEMA)
    incoming_theme_ids = [
        row.theme_id for row in incoming.select("theme_id").distinct().collect()
    ]
    pending_rows = (
        _read_pending_state(spark)
        .unionByName(incoming)
        .dropDuplicates(["article_id"])
        .rdd.persist(StorageLevel.MEMORY_AND_DISK)
    )

    try:
        # DataFrame.cache()가 만드는 PartitionKeyedAccumulator는 Spark 4.2.0의
        # SPARK-59451을 유발할 수 있다. 일반 RDD를 먼저 materialize하고 그 위에
        # DataFrame을 다시 만들어 이후 action들이 동일한 파티션을 재사용하게 한다.
        pending_rows.count()
        pending = spark.createDataFrame(pending_rows, schema=PENDING_SCHEMA).filter(
            F.to_timestamp("published_at")
            >= F.expr(
                f"current_timestamp() - INTERVAL {ISSUE_CLUSTER_WINDOW_HOURS} HOURS"
            )
        )

        triggered_theme_ids = [
            row.theme_id
            for row in pending.groupBy("theme_id")
            .count()
            .filter(
                (F.col("count") >= ISSUE_CLUSTER_TRIGGER_COUNT)
                & F.col("theme_id").isin(incoming_theme_ids)
            )
            .select("theme_id")
            .collect()
        ]
        assigned_article_ids: set[str] = set()
        event_rows: list[tuple[str, str]] = []
        generated_candidates = []

        if triggered_theme_ids:
            theme_names = _load_theme_names(spark, triggered_theme_ids)
            for theme_id in sorted(triggered_theme_ids):
                theme_name = theme_names.get(theme_id)
                if theme_name is None:
                    raise RuntimeError(f"Theme {theme_id} does not exist")
                selected = [
                    _to_article(row)
                    for row in pending.filter(F.col("theme_id") == theme_id)
                    .orderBy("unclassified_at", "article_id")
                    .limit(ISSUE_CLUSTER_MAX_ARTICLES_PER_THEME)
                    .collect()
                ]

                # 이슈 군집에 실제로 포함된 기사만 소비한다. HDBSCAN noise와
                # 개별 membership/centroid 응집도 기준을 통과하지 못한 기사는
                # 72시간 동안 pending에 남겨 후속 기사와 다시 군집화할 기회를 준다.
                clusters = cluster_articles(
                    selected,
                    min_cluster_size=ISSUE_CLUSTER_MIN_SIZE,
                    min_samples=ISSUE_CLUSTER_MIN_SAMPLES,
                    representative_count=ISSUE_CLUSTER_REPRESENTATIVE_COUNT,
                    min_membership_confidence=ISSUE_CLUSTER_MIN_MEMBER_CONFIDENCE,
                    min_centroid_similarity=ISSUE_CLUSTER_MIN_CENTROID_SIMILARITY,
                )
                for cluster in clusters:
                    try:
                        decision = generate_issue(GMS_CONFIG, theme_name, cluster)
                    except GmsIssueGenerationError as exc:
                        print(
                            f"Skipped issue generation: "
                            f"batch_id={batch_id} "
                            f"theme_id={theme_id} "
                            f"article_count={len(cluster.articles)} "
                            f"reason={exc}",
                            flush=True,
                        )
                        continue

                    filtered_cluster = filter_cluster_articles(
                        cluster,
                        decision.included_article_ids,
                        min_cluster_size=ISSUE_CLUSTER_MIN_SIZE,
                        representative_count=ISSUE_CLUSTER_REPRESENTATIVE_COUNT,
                        min_centroid_similarity=(
                            ISSUE_CLUSTER_MIN_CENTROID_SIMILARITY
                        ),
                    )
                    if filtered_cluster is None:
                        print(
                            "Skipped issue after event membership validation: "
                            f"batch_id={batch_id} "
                            f"theme_id={theme_id} "
                            f"candidate_count={len(cluster.articles)} "
                            f"included_count={len(decision.included_article_ids)} "
                            f"minimum={ISSUE_CLUSTER_MIN_SIZE}",
                            flush=True,
                        )
                        continue

                    generated_candidates.append(
                        (filtered_cluster, decision.issue)
                    )
                    assigned_article_ids.update(
                        article.article_id for article in filtered_cluster.articles
                    )

        for cluster, generated in merge_generated_issue_candidates(
            generated_candidates,
            representative_count=ISSUE_CLUSTER_REPRESENTATIVE_COUNT,
        ):
            event_rows.extend(build_issue_events(cluster, generated))

        if event_rows:
            event_df = spark.createDataFrame(event_rows, schema=EVENT_SCHEMA)
            (
                event_df.write.format("kafka")
                .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
                .option("topic", KAFKA_EVENT_TOPIC)
                .save()
            )

        materialized_remaining = pending
        remaining_rows = None
        if assigned_article_ids:
            processed_df = spark.createDataFrame(
                [(article_id,) for article_id in sorted(assigned_article_ids)],
                schema=StructType(
                    [StructField("article_id", StringType(), nullable=False)]
                ),
            )
            remaining = pending.join(
                F.broadcast(processed_df), on="article_id", how="left_anti"
            )
            remaining_rows = remaining.rdd.persist(StorageLevel.MEMORY_AND_DISK)
        try:
            if remaining_rows is not None:
                # 기존 상태 경로를 교체하기 전에 결과를 완전히 고정한다.
                remaining_rows.count()
                materialized_remaining = spark.createDataFrame(
                    remaining_rows, schema=PENDING_SCHEMA
                )
            _write_pending_state(spark, materialized_remaining, batch_id)
        finally:
            if remaining_rows is not None:
                remaining_rows.unpersist()
        print(
            f"Completed unclassified cluster batch {batch_id}: "
            f"events={len(event_rows)} assigned={len(assigned_article_ids)}"
        )
    finally:
        pending_rows.unpersist()
        parsed_rows.unpersist()


def _validate_config() -> None:
    if not POSTGRESQL_URL or not POSTGRESQL_USER or not POSTGRESQL_PASSWORD:
        raise RuntimeError("DB connection environment variables are required")
    if not GMS_CONFIG.api_key.strip():
        raise RuntimeError("GMS_API_KEY is required")
    if ISSUE_CLUSTER_TRIGGER_COUNT < 2:
        raise ValueError("ISSUE_CLUSTER_TRIGGER_COUNT must be at least 2")
    if not 2 <= ISSUE_CLUSTER_MIN_SIZE <= ISSUE_CLUSTER_TRIGGER_COUNT:
        raise ValueError(
            "ISSUE_CLUSTER_MIN_SIZE must be between 2 and the trigger count"
        )
    if ISSUE_CLUSTER_MIN_SAMPLES < 1:
        raise ValueError("ISSUE_CLUSTER_MIN_SAMPLES must be positive")
    if ISSUE_CLUSTER_MAX_ARTICLES_PER_THEME < ISSUE_CLUSTER_TRIGGER_COUNT:
        raise ValueError(
            "ISSUE_CLUSTER_MAX_ARTICLES_PER_THEME must be at least the trigger count"
        )
    if GMS_CONFIG.timeout_seconds <= 0:
        raise ValueError("GMS_TIMEOUT_SECONDS must be positive")
    if GMS_CONFIG.max_attempts < 1:
        raise ValueError("GMS_MAX_ATTEMPTS must be positive")
    if not 0.0 <= ISSUE_CLUSTER_MIN_MEMBER_CONFIDENCE <= 1.0:
        raise ValueError(
            "ISSUE_CLUSTER_MIN_MEMBER_CONFIDENCE must be between 0 and 1"
        )
    if not -1.0 <= ISSUE_CLUSTER_MIN_CENTROID_SIMILARITY <= 1.0:
        raise ValueError(
            "ISSUE_CLUSTER_MIN_CENTROID_SIMILARITY must be between -1 and 1"
        )


def main() -> None:
    _validate_config()
    spark = SparkSession.builder.appName("news-unclassified-issue-stream-v1").getOrCreate()
    spark.sparkContext.setLogLevel(os.getenv("SPARK_LOG_LEVEL", "WARN"))
    register_streaming_metrics(spark, "news-unclassified-issue-stream-v1")
    stream = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BOOTSTRAP_SERVERS)
        .option("subscribe", KAFKA_UNCLASSIFIED_TOPIC)
        .option("startingOffsets", SPARK_STARTING_OFFSETS)
        .option("failOnDataLoss", "true")
        .load()
    )
    query = (
        stream.writeStream.foreachBatch(write_cluster_batch)
        .trigger(processingTime="15 seconds")
        .option("checkpointLocation", SPARK_CHECKPOINT_LOCATION)
        .queryName("news-unclassified-issue-stream-v1")
        .start()
    )
    query.awaitTermination()


if __name__ == "__main__":
    main()
