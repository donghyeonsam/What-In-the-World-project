""" Spark stream: news.unclassified.v1 -> clustered issue events."""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone

from gms_issue_generator import (
    GmsConfig,
    GmsIssueGenerationError,
    GmsRateLimitError,
    GmsTransientError,
    generate_issue,
)
from issue_clustering import (
    ClusterAttempt,
    InvalidUnclassifiedArticle,
    UnclassifiedArticle,
    build_issue_events,
    cluster_articles,
    cluster_membership_key,
    decide_cluster_attempt,
    filter_cluster_articles,
    merge_generated_issue_candidates,
    parse_unclassified_message,
    record_cluster_attempt,
    should_trigger_theme_clustering,
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
ISSUE_CLUSTER_IMMEDIATE_RETRIGGER_COUNT = 50
ISSUE_CLUSTER_DELAYED_RETRIGGER_COUNT = 10
ISSUE_CLUSTER_DELAYED_RETRIGGER_MINUTES = 60
ISSUE_CLUSTER_MIN_SIZE = 8
ISSUE_CLUSTER_MIN_SAMPLES = 4
ISSUE_CLUSTER_MIN_MEMBER_CONFIDENCE = 0.80
ISSUE_CLUSTER_MIN_CENTROID_SIMILARITY = 0.92
ISSUE_CLUSTER_WINDOW_HOURS = 72
ISSUE_CLUSTER_ATTEMPT_TTL_HOURS = 72
ISSUE_CLUSTER_REPRESENTATIVE_COUNT = 4
ISSUE_CLUSTER_MAX_ARTICLES_PER_THEME = int(
    os.getenv("ISSUE_CLUSTER_MAX_ARTICLES_PER_THEME", "2000")
)
GMS_BASE_URL = (
    "https://gms.ssafy.io/gmsapi/"
    "generativelanguage.googleapis.com/v1beta"
)
GMS_MODEL = os.getenv("GMS_MODEL", "gemini-2.5-flash-lite")
GMS_TIMEOUT_SECONDS = 30.0
# 같은 요청 똑같이 보낼 수 있는 데드라인
GMS_MAX_ATTEMPTS = int(os.getenv("GMS_MAX_ATTEMPTS", "2"))
# 429 응답에 Retry-After가 없으면 GMS 호출을 60초 동안 중단한다.
GMS_RATE_LIMIT_COOLDOWN_SECONDS = float(
    os.getenv("GMS_RATE_LIMIT_COOLDOWN_SECONDS", "60")
)
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
ATTEMPT_STATE_LOCATION = os.getenv(
    "ISSUE_CLUSTER_ATTEMPT_STATE_LOCATION",
    "hdfs://namenode:9000/checkpoints/unclassified-issue-attempt-state-v1",
)
TRIGGER_STATE_LOCATION = os.getenv(
    "ISSUE_CLUSTER_TRIGGER_STATE_LOCATION",
    "hdfs://namenode:9000/checkpoints/unclassified-issue-trigger-state-v1",
)
SPARK_STARTING_OFFSETS = os.getenv("ISSUE_CLUSTER_STARTING_OFFSETS", "earliest")

_gms_blocked_until = 0.0


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

ATTEMPT_SCHEMA = StructType(
    [
        StructField("lineage_id", StringType(), nullable=False),
        StructField("theme_id", LongType(), nullable=False),
        StructField(
            "article_ids", ArrayType(StringType(), containsNull=False), nullable=False
        ),
        StructField("attempted_at", StringType(), nullable=False),
    ]
)

TRIGGER_STATE_SCHEMA = StructType(
    [
        StructField("theme_id", LongType(), nullable=False),
        StructField("new_since_last_cluster", LongType(), nullable=False),
        StructField("last_clustered_at", StringType(), nullable=True),
        StructField("last_counted_batch_id", LongType(), nullable=False),
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


def _write_state(
    spark: SparkSession,
    data,
    location: str,
    batch_id: int,
    state_name: str,
) -> None:
    final_path = spark._jvm.org.apache.hadoop.fs.Path(location)
    temporary_path = spark._jvm.org.apache.hadoop.fs.Path(
        f"{location}.__tmp_{batch_id}"
    )
    backup_path = spark._jvm.org.apache.hadoop.fs.Path(f"{location}.__backup")
    file_system = final_path.getFileSystem(spark._jsc.hadoopConfiguration())

    if file_system.exists(temporary_path):
        file_system.delete(temporary_path, True)
    data.coalesce(1).write.mode("overwrite").parquet(temporary_path.toString())

    if file_system.exists(backup_path):
        file_system.delete(backup_path, True)
    had_previous_state = file_system.exists(final_path)
    if had_previous_state and not file_system.rename(final_path, backup_path):
        raise RuntimeError(f"Could not back up the {state_name} state")
    if not file_system.rename(temporary_path, final_path):
        if had_previous_state and file_system.exists(backup_path):
            file_system.rename(backup_path, final_path)
        raise RuntimeError(f"Could not publish the {state_name} state")
    if file_system.exists(backup_path):
        file_system.delete(backup_path, True)


def _write_pending_state(spark: SparkSession, remaining, batch_id: int) -> None:
    _write_state(
        spark,
        remaining,
        PENDING_STATE_LOCATION,
        batch_id,
        "pending issue",
    )


def _read_attempt_state(spark: SparkSession):
    hadoop_path = spark._jvm.org.apache.hadoop.fs.Path(ATTEMPT_STATE_LOCATION)
    backup_path = spark._jvm.org.apache.hadoop.fs.Path(
        f"{ATTEMPT_STATE_LOCATION}.__backup"
    )
    file_system = hadoop_path.getFileSystem(spark._jsc.hadoopConfiguration())
    if not file_system.exists(hadoop_path) and file_system.exists(backup_path):
        if not file_system.rename(backup_path, hadoop_path):
            raise RuntimeError("Could not recover the issue attempt state")
    if not _path_exists(spark, ATTEMPT_STATE_LOCATION):
        return spark.createDataFrame([], schema=ATTEMPT_SCHEMA)
    return spark.read.schema(ATTEMPT_SCHEMA).parquet(ATTEMPT_STATE_LOCATION)


def _write_attempt_state(spark: SparkSession, attempts, batch_id: int) -> None:
    _write_state(
        spark,
        attempts,
        ATTEMPT_STATE_LOCATION,
        batch_id,
        "issue attempt",
    )


def _read_trigger_state(spark: SparkSession):
    hadoop_path = spark._jvm.org.apache.hadoop.fs.Path(TRIGGER_STATE_LOCATION)
    backup_path = spark._jvm.org.apache.hadoop.fs.Path(
        f"{TRIGGER_STATE_LOCATION}.__backup"
    )
    file_system = hadoop_path.getFileSystem(spark._jsc.hadoopConfiguration())
    if not file_system.exists(hadoop_path) and file_system.exists(backup_path):
        if not file_system.rename(backup_path, hadoop_path):
            raise RuntimeError("Could not recover the issue trigger state")
    if not _path_exists(spark, TRIGGER_STATE_LOCATION):
        return spark.createDataFrame([], schema=TRIGGER_STATE_SCHEMA)
    return spark.read.schema(TRIGGER_STATE_SCHEMA).parquet(TRIGGER_STATE_LOCATION)


def _write_trigger_state(spark: SparkSession, triggers, batch_id: int) -> None:
    _write_state(
        spark,
        triggers,
        TRIGGER_STATE_LOCATION,
        batch_id,
        "issue trigger",
    )


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


def _to_attempt(row) -> ClusterAttempt:
    article_ids = tuple(sorted(row.article_ids))
    return ClusterAttempt(
        # Recompute the exact-membership key so state written by the previous
        # evolving-lineage policy migrates automatically on its next write.
        lineage_id=cluster_membership_key(row.theme_id, article_ids),
        theme_id=row.theme_id,
        article_ids=article_ids,
        attempted_at=row.attempted_at,
    )


def write_cluster_batch(batch_df, batch_id: int) -> None:
    global _gms_blocked_until

    spark = batch_df.sparkSession
    parsed_rows = batch_df.selectExpr(
        "CAST(key AS STRING) AS key",
        "CAST(value AS STRING) AS value",
        "partition",
        "offset",
    ).rdd.mapPartitions(_parse_partition).persist(StorageLevel.MEMORY_AND_DISK)
    incoming = spark.createDataFrame(parsed_rows, schema=PENDING_SCHEMA)
    pending_source = (
        _read_pending_state(spark)
        .unionByName(incoming)
        .dropDuplicates(["article_id"])
    )
    pending_rows = pending_source.rdd.persist(StorageLevel.MEMORY_AND_DISK)

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
        attempt_rows = (
            _read_attempt_state(spark)
            .filter(
                F.to_timestamp("attempted_at")
                >= F.expr(
                    "current_timestamp() - INTERVAL "
                    f"{ISSUE_CLUSTER_ATTEMPT_TTL_HOURS} HOURS"
                )
            )
            .collect()
        )
        attempts_by_lineage = {
            attempt.lineage_id: attempt
            for attempt in (_to_attempt(row) for row in attempt_rows)
        }

        trigger_rows = _read_trigger_state(spark).collect()
        trigger_state_by_theme = {
            int(row.theme_id): {
                "new_since_last_cluster": int(row.new_since_last_cluster),
                "last_clustered_at": row.last_clustered_at,
                "last_counted_batch_id": int(row.last_counted_batch_id),
            }
            for row in trigger_rows
        }
        if len(trigger_state_by_theme) != len(trigger_rows):
            raise RuntimeError("Issue trigger state contains duplicate theme ids")

        incoming_counts = (
            incoming.dropDuplicates(["article_id"])
            .groupBy("theme_id")
            .count()
            .collect()
        )
        for row in incoming_counts:
            theme_id = int(row.theme_id)
            state = trigger_state_by_theme.setdefault(
                theme_id,
                {
                    "new_since_last_cluster": 0,
                    "last_clustered_at": None,
                    "last_counted_batch_id": -1,
                },
            )
            if batch_id > state["last_counted_batch_id"]:
                state["new_since_last_cluster"] += int(row["count"])
                state["last_counted_batch_id"] = batch_id

        pending_counts = pending.groupBy("theme_id").count().collect()
        trigger_evaluated_at = datetime.now(timezone.utc)
        triggered_theme_ids = sorted(
            int(row.theme_id)
            for row in pending_counts
            if should_trigger_theme_clustering(
                int(row["count"]),
                int(
                    trigger_state_by_theme.get(int(row.theme_id), {}).get(
                        "new_since_last_cluster", 0
                    )
                ),
                trigger_state_by_theme.get(int(row.theme_id), {}).get(
                    "last_clustered_at"
                ),
                now=trigger_evaluated_at,
                initial_trigger_count=ISSUE_CLUSTER_TRIGGER_COUNT,
                minimum_pending_count=ISSUE_CLUSTER_MIN_SIZE,
                immediate_retrigger_count=ISSUE_CLUSTER_IMMEDIATE_RETRIGGER_COUNT,
                delayed_retrigger_count=ISSUE_CLUSTER_DELAYED_RETRIGGER_COUNT,
                delayed_retrigger_minutes=ISSUE_CLUSTER_DELAYED_RETRIGGER_MINUTES,
            )
        )
        assigned_article_ids: set[str] = set()
        event_rows: list[tuple[str, str]] = []
        generated_candidates = []
        gms_candidate_count = 0
        gms_halt_reason: str | None = None
        completed_theme_ids: set[int] = set()

        if time.time() < _gms_blocked_until:
            gms_halt_reason = "rate_limit_cooldown"
            print(
                "Skipped GMS generation during rate-limit cooldown: "
                f"batch_id={batch_id} "
                f"remaining_seconds={max(0, int(_gms_blocked_until - time.time()))}",
                flush=True,
            )

        if triggered_theme_ids and gms_halt_reason is None:
            theme_names = _load_theme_names(spark, triggered_theme_ids)
            for theme_id in sorted(triggered_theme_ids):
                if gms_halt_reason is not None:
                    break
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
                    retry_decision = decide_cluster_attempt(
                        cluster,
                        attempts_by_lineage,
                    )
                    if not retry_decision.should_attempt:
                        print(
                            "Skipped previously attempted issue cluster: "
                            f"batch_id={batch_id} "
                            f"theme_id={theme_id} "
                            f"article_count={len(cluster.articles)} "
                            f"reason={retry_decision.reason}",
                            flush=True,
                        )
                        continue

                    gms_candidate_count += 1
                    attempted_at = datetime.now(timezone.utc).isoformat()
                    try:
                        decision = generate_issue(GMS_CONFIG, theme_name, cluster)
                    except GmsRateLimitError as exc:
                        cooldown_seconds = (
                            exc.retry_after_seconds
                            if exc.retry_after_seconds is not None
                            else GMS_RATE_LIMIT_COOLDOWN_SECONDS
                        )
                        _gms_blocked_until = max(
                            _gms_blocked_until,
                            time.time() + max(1.0, cooldown_seconds),
                        )
                        gms_halt_reason = "rate_limited"
                        print(
                            "Stopped GMS generation after rate limit: "
                            f"batch_id={batch_id} "
                            f"theme_id={theme_id} "
                            f"article_count={len(cluster.articles)} "
                            f"cooldown_seconds={max(1, int(cooldown_seconds))}",
                            flush=True,
                        )
                        break
                    except GmsTransientError as exc:
                        print(
                            "Skipped issue generation after transient failure: "
                            f"batch_id={batch_id} "
                            f"theme_id={theme_id} "
                            f"article_count={len(cluster.articles)} "
                            f"reason={exc}",
                            flush=True,
                        )
                        continue
                    except GmsIssueGenerationError as exc:
                        attempt = record_cluster_attempt(
                            cluster,
                            attempted_at,
                        )
                        attempts_by_lineage[attempt.lineage_id] = attempt
                        print(
                            "Skipped issue generation after response validation: "
                            f"batch_id={batch_id} "
                            f"theme_id={theme_id} "
                            f"article_count={len(cluster.articles)} "
                            f"reason={exc}",
                            flush=True,
                        )
                        continue

                    attempt = record_cluster_attempt(cluster, attempted_at)
                    attempts_by_lineage[attempt.lineage_id] = attempt
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
                if gms_halt_reason is None:
                    completed_theme_ids.add(theme_id)

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

        attempt_values = [
            (
                attempt.lineage_id,
                attempt.theme_id,
                list(attempt.article_ids),
                attempt.attempted_at,
            )
            for attempt in sorted(
                attempts_by_lineage.values(), key=lambda item: item.lineage_id
            )
        ]
        attempt_state = spark.createDataFrame(attempt_values, schema=ATTEMPT_SCHEMA)
        _write_attempt_state(spark, attempt_state, batch_id)

        clustered_at = datetime.now(timezone.utc).isoformat()
        for theme_id in completed_theme_ids:
            state = trigger_state_by_theme.setdefault(
                theme_id,
                {
                    "new_since_last_cluster": 0,
                    "last_clustered_at": None,
                    "last_counted_batch_id": batch_id,
                },
            )
            state["new_since_last_cluster"] = 0
            state["last_clustered_at"] = clustered_at
        trigger_values = [
            (
                theme_id,
                state["new_since_last_cluster"],
                state["last_clustered_at"],
                state["last_counted_batch_id"],
            )
            for theme_id, state in sorted(
                trigger_state_by_theme.items()
            )
        ]
        materialized_trigger_state = spark.createDataFrame(
            trigger_values, schema=TRIGGER_STATE_SCHEMA
        )
        _write_trigger_state(spark, materialized_trigger_state, batch_id)
        print(
            f"Completed unclassified cluster batch {batch_id}: "
            f"events={len(event_rows)} assigned={len(assigned_article_ids)} "
            f"triggered_themes={len(triggered_theme_ids)} "
            f"gms_candidates={gms_candidate_count} "
            f"gms_halt_reason={gms_halt_reason or 'none'}"
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
    if ISSUE_CLUSTER_IMMEDIATE_RETRIGGER_COUNT < ISSUE_CLUSTER_DELAYED_RETRIGGER_COUNT:
        raise ValueError(
            "Immediate retrigger count must be at least the delayed retrigger count"
        )
    if ISSUE_CLUSTER_DELAYED_RETRIGGER_COUNT < ISSUE_CLUSTER_MIN_SIZE:
        raise ValueError(
            "Delayed retrigger count must be at least the minimum cluster size"
        )
    if ISSUE_CLUSTER_DELAYED_RETRIGGER_MINUTES < 1:
        raise ValueError("Delayed retrigger minutes must be positive")
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
    if GMS_RATE_LIMIT_COOLDOWN_SECONDS <= 0:
        raise ValueError("GMS_RATE_LIMIT_COOLDOWN_SECONDS must be positive")
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
