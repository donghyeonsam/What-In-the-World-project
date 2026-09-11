"""Stable Prometheus metrics for PySpark Structured Streaming drivers."""

from __future__ import annotations

import json
import logging
import os
import time
from collections.abc import Mapping

from prometheus_client import Counter, Gauge, Histogram, start_http_server
from pyspark.sql.streaming import StreamingQueryListener


logger = logging.getLogger(__name__)

QUERY_UP = Gauge(
    "witw_spark_streaming_query_up",
    "Whether a Structured Streaming query is running.",
    ("app", "query"),
)
LAST_PROGRESS = Gauge(
    "witw_spark_streaming_last_progress_timestamp_seconds",
    "Unix timestamp of the latest completed micro-batch.",
    ("app", "query"),
)
BATCH_ID = Gauge(
    "witw_spark_streaming_batch_id",
    "Latest Structured Streaming batch identifier.",
    ("app", "query"),
)
INPUT_ROWS = Counter(
    "witw_spark_streaming_input_rows_total",
    "Rows accepted by completed Structured Streaming micro-batches.",
    ("app", "query"),
)
INPUT_RATE = Gauge(
    "witw_spark_streaming_input_rows_per_second",
    "Input row rate reported for the latest micro-batch.",
    ("app", "query"),
)
PROCESS_RATE = Gauge(
    "witw_spark_streaming_processed_rows_per_second",
    "Processing row rate reported for the latest micro-batch.",
    ("app", "query"),
)
BATCH_DURATION = Histogram(
    "witw_spark_streaming_batch_duration_seconds",
    "Structured Streaming trigger execution duration.",
    ("app", "query"),
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60, 120, 300),
)
SOURCE_OFFSET = Gauge(
    "witw_spark_streaming_source_offset",
    "Latest offset completed by Spark for a Kafka topic-partition.",
    ("app", "query", "topic", "partition"),
)
STATE_ROWS = Gauge(
    "witw_spark_streaming_state_rows",
    "Rows held by a Structured Streaming state operator.",
    ("app", "query", "operator"),
)
QUERY_TERMINATIONS = Counter(
    "witw_spark_streaming_query_terminations_total",
    "Structured Streaming query terminations by result.",
    ("app", "query", "result"),
)


def _value(obj, name, default=None):
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _as_mapping(value) -> dict:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _query_name(event_or_progress) -> str:
    return str(_value(event_or_progress, "name", None) or "unnamed")


class PrometheusStreamingQueryListener(StreamingQueryListener):
    def __init__(self, app_name: str):
        super().__init__()
        self.app_name = app_name
        self._query_names: dict[str, str] = {}

    def onQueryStarted(self, event) -> None:  # noqa: N802 - Spark callback API
        query = _query_name(event)
        self._query_names[str(_value(event, "runId", ""))] = query
        QUERY_UP.labels(self.app_name, query).set(1)

    def onQueryProgress(self, event) -> None:  # noqa: N802 - Spark callback API
        progress = event.progress
        query = _query_name(progress)
        self._query_names[str(_value(progress, "runId", ""))] = query
        QUERY_UP.labels(self.app_name, query).set(1)
        LAST_PROGRESS.labels(self.app_name, query).set(time.time())
        BATCH_ID.labels(self.app_name, query).set(float(_value(progress, "batchId", 0)))
        INPUT_ROWS.labels(self.app_name, query).inc(
            float(_value(progress, "numInputRows", 0) or 0)
        )
        INPUT_RATE.labels(self.app_name, query).set(
            float(_value(progress, "inputRowsPerSecond", 0) or 0)
        )
        PROCESS_RATE.labels(self.app_name, query).set(
            float(_value(progress, "processedRowsPerSecond", 0) or 0)
        )

        durations = _as_mapping(_value(progress, "durationMs", {}))
        trigger_ms = float(durations.get("triggerExecution", 0) or 0)
        BATCH_DURATION.labels(self.app_name, query).observe(trigger_ms / 1000.0)

        for source in _value(progress, "sources", ()) or ():
            end_offsets = _as_mapping(_value(source, "endOffset", {}))
            for topic, partitions in end_offsets.items():
                if not isinstance(partitions, Mapping):
                    continue
                for partition, offset in partitions.items():
                    try:
                        SOURCE_OFFSET.labels(
                            self.app_name, query, str(topic), str(partition)
                        ).set(float(offset))
                    except (TypeError, ValueError):
                        logger.warning(
                            "Ignoring non-numeric Spark offset topic=%s partition=%s: %r",
                            topic,
                            partition,
                            offset,
                        )

        for index, operator in enumerate(
            _value(progress, "stateOperators", ()) or ()
        ):
            rows = float(_value(operator, "numRowsTotal", 0) or 0)
            STATE_ROWS.labels(self.app_name, query, str(index)).set(rows)

    def onQueryIdle(self, event) -> None:  # noqa: N802 - Spark callback API
        # An idle notification means the query is healthy but has no new input.
        run_id = str(_value(event, "runId", ""))
        query = self._query_names.get(run_id, _query_name(event))
        QUERY_UP.labels(self.app_name, query).set(1)

    def onQueryTerminated(self, event) -> None:  # noqa: N802 - Spark callback API
        run_id = str(_value(event, "runId", ""))
        query = self._query_names.pop(run_id, _query_name(event))
        exception = _value(event, "exception", None)
        QUERY_UP.labels(self.app_name, query).set(0)
        QUERY_TERMINATIONS.labels(
            self.app_name, query, "failed" if exception else "stopped"
        ).inc()


def register_streaming_metrics(spark, app_name: str) -> None:
    host = os.getenv("SPARK_METRICS_HOST", "0.0.0.0")
    port = int(os.getenv("SPARK_METRICS_PORT", "9102"))
    if not 1 <= port <= 65535:
        raise ValueError("SPARK_METRICS_PORT must be between 1 and 65535")
    start_http_server(port, addr=host)
    spark.streams.addListener(PrometheusStreamingQueryListener(app_name))
    logger.info("Spark streaming metrics listening on http://%s:%d/metrics", host, port)
