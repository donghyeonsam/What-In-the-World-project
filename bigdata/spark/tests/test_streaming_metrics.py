import importlib.util
import pathlib
import sys
import types
import unittest
from unittest.mock import patch


class _NoopMetric:
    def __init__(self, *args, **kwargs):
        pass

    def labels(self, *args, **kwargs):
        return self

    def inc(self, value=1):
        pass

    def set(self, value):
        pass

    def observe(self, value):
        pass


prometheus_stub = types.ModuleType("prometheus_client")
prometheus_stub.Counter = _NoopMetric
prometheus_stub.Gauge = _NoopMetric
prometheus_stub.Histogram = _NoopMetric
prometheus_stub.start_http_server = lambda *args, **kwargs: None

pyspark_stub = types.ModuleType("pyspark")
pyspark_sql_stub = types.ModuleType("pyspark.sql")
pyspark_streaming_stub = types.ModuleType("pyspark.sql.streaming")
pyspark_streaming_stub.StreamingQueryListener = object

MODULE_PATH = pathlib.Path(__file__).parents[1] / "apps" / "streaming_metrics.py"
SPEC = importlib.util.spec_from_file_location("streaming_metrics_under_test", MODULE_PATH)
metrics = importlib.util.module_from_spec(SPEC)
with patch.dict(
    sys.modules,
    {
        "prometheus_client": prometheus_stub,
        "pyspark": pyspark_stub,
        "pyspark.sql": pyspark_sql_stub,
        "pyspark.sql.streaming": pyspark_streaming_stub,
    },
):
    SPEC.loader.exec_module(metrics)


class _Recorder:
    def __init__(self):
        self.calls = []
        self.label_values = ()

    def labels(self, *values):
        child = _Recorder()
        child.calls = self.calls
        child.label_values = values
        return child

    def inc(self, value=1):
        self.calls.append(("inc", self.label_values, value))

    def set(self, value):
        self.calls.append(("set", self.label_values, value))

    def observe(self, value):
        self.calls.append(("observe", self.label_values, value))


class StreamingMetricsTest(unittest.TestCase):
    def test_progress_exports_kafka_partition_offsets(self):
        recorders = {
            name: _Recorder()
            for name in (
                "QUERY_UP",
                "LAST_PROGRESS",
                "BATCH_ID",
                "INPUT_ROWS",
                "INPUT_RATE",
                "PROCESS_RATE",
                "BATCH_DURATION",
                "SOURCE_OFFSET",
                "STATE_ROWS",
            )
        }
        progress = types.SimpleNamespace(
            name="query-a",
            runId="run-a",
            batchId=3,
            numInputRows=20,
            inputRowsPerSecond=4.0,
            processedRowsPerSecond=5.0,
            durationMs={"triggerExecution": 2500},
            sources=[
                types.SimpleNamespace(endOffset='{"news.enriched.v1":{"0":12,"1":15}}')
            ],
            stateOperators=[],
        )
        listener = metrics.PrometheusStreamingQueryListener("app-a")

        with patch.multiple(metrics, **recorders):
            listener.onQueryProgress(types.SimpleNamespace(progress=progress))

        self.assertIn(
            ("set", ("app-a", "query-a", "news.enriched.v1", "0"), 12.0),
            recorders["SOURCE_OFFSET"].calls,
        )
        self.assertIn(
            ("observe", ("app-a", "query-a"), 2.5),
            recorders["BATCH_DURATION"].calls,
        )

    def test_non_json_offset_is_ignored(self):
        self.assertEqual({}, metrics._as_mapping("not json"))


if __name__ == "__main__":
    unittest.main()
