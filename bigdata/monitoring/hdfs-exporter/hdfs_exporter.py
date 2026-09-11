"""Small dependency-free Prometheus exporter for HDFS JMX and WebHDFS."""

from __future__ import annotations

import os
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


NAMENODE_URL = os.getenv("HDFS_NAMENODE_HTTP_URL", "http://namenode:9870").rstrip("/")
DATANODE_URL = os.getenv("HDFS_DATANODE_HTTP_URL", "http://datanode:9864").rstrip("/")
TIMEOUT_SECONDS = float(os.getenv("HDFS_EXPORTER_TIMEOUT_SECONDS", "5"))
PATHS = tuple(
    path.strip()
    for path in os.getenv(
        "HDFS_MONITORED_PATHS",
        "/data/news/bronze/news.raw.v1,/data/news/silver/news.enriched.v1,/checkpoints",
    ).split(",")
    if path.strip()
)


NAME_NODE_METRICS = {
    "hdfs_capacity_total_bytes": ("CapacityTotal",),
    "hdfs_capacity_used_bytes": ("CapacityUsed", "CapacityUsedGB"),
    "hdfs_capacity_remaining_bytes": ("CapacityRemaining",),
    "hdfs_files_total": ("FilesTotal",),
    "hdfs_blocks_total": ("BlocksTotal",),
    "hdfs_missing_blocks": ("MissingBlocks",),
    "hdfs_under_replicated_blocks": ("UnderReplicatedBlocks",),
    "hdfs_pending_replication_blocks": ("PendingReplicationBlocks",),
    "hdfs_live_datanodes": ("NumLiveDataNodes",),
    "hdfs_dead_datanodes": ("NumDeadDataNodes",),
    "hdfs_volume_failures_total": ("VolumeFailuresTotal",),
}

DATA_NODE_METRICS = {
    "hdfs_datanode_capacity_bytes": ("Capacity",),
    "hdfs_datanode_used_bytes": ("DfsUsed",),
    "hdfs_datanode_remaining_bytes": ("Remaining",),
    "hdfs_datanode_failed_volumes": ("NumFailedVolumes",),
}


def _fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:
        import json

        return json.load(response)


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _first_numeric(beans: list[dict], aliases: tuple[str, ...]):
    for bean in beans:
        for alias in aliases:
            value = _number(bean.get(alias))
            if value is not None:
                # CapacityUsedGB is retained only as a compatibility fallback.
                return value * (1024**3) if alias.endswith("GB") else value
    return None


def _label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _sample(name: str, value: float, labels: dict[str, str] | None = None) -> str:
    rendered_labels = ""
    if labels:
        rendered_labels = "{" + ",".join(
            f'{key}="{_label(label)}"' for key, label in sorted(labels.items())
        ) + "}"
    return f"{name}{rendered_labels} {value:g}"


def _jmx_metrics(base_url: str, definitions: dict[str, tuple[str, ...]]) -> list[str]:
    payload = _fetch_json(f"{base_url}/jmx")
    beans = payload.get("beans", [])
    if not isinstance(beans, list):
        raise ValueError(f"Invalid JMX response from {base_url}")
    samples = []
    for metric_name, aliases in definitions.items():
        value = _first_numeric(beans, aliases)
        if value is not None:
            samples.append(_sample(metric_name, value))
    return samples


def _path_metrics(path: str) -> list[str]:
    encoded_path = urllib.parse.quote(path, safe="/")
    url = (
        f"{NAMENODE_URL}/webhdfs/v1{encoded_path}"
        "?op=GETCONTENTSUMMARY&user.name=root"
    )
    summary = _fetch_json(url).get("ContentSummary", {})
    labels = {"path": path}
    definitions = {
        "hdfs_path_length_bytes": "length",
        "hdfs_path_space_consumed_bytes": "spaceConsumed",
        "hdfs_path_files": "fileCount",
        "hdfs_path_directories": "directoryCount",
    }
    samples = []
    for metric_name, key in definitions.items():
        value = _number(summary.get(key))
        if value is not None:
            samples.append(_sample(metric_name, value, labels))
    return samples


def collect_metrics() -> str:
    started_at = time.perf_counter()
    samples = []
    core_success = True
    for target, url, definitions in (
        ("namenode", NAMENODE_URL, NAME_NODE_METRICS),
        ("datanode", DATANODE_URL, DATA_NODE_METRICS),
    ):
        try:
            samples.extend(_jmx_metrics(url, definitions))
        except Exception:
            core_success = False
            samples.append(_sample("hdfs_exporter_target_up", 0, {"target": target}))
        else:
            samples.append(_sample("hdfs_exporter_target_up", 1, {"target": target}))

    for path in PATHS:
        try:
            samples.extend(_path_metrics(path))
        except Exception:
            samples.append(_sample("hdfs_exporter_path_up", 0, {"path": path}))
        else:
            samples.append(_sample("hdfs_exporter_path_up", 1, {"path": path}))

    samples.append(_sample("hdfs_exporter_scrape_success", int(core_success)))
    samples.append(
        _sample("hdfs_exporter_scrape_duration_seconds", time.perf_counter() - started_at)
    )
    return "\n".join(samples) + "\n"


class MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        if self.path not in ("/", "/metrics"):
            self.send_error(404)
            return
        payload = collect_metrics().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        return


def main() -> None:
    host = os.getenv("HDFS_EXPORTER_HOST", "0.0.0.0")
    port = int(os.getenv("HDFS_EXPORTER_PORT", "9120"))
    if not 1 <= port <= 65535:
        raise ValueError("HDFS_EXPORTER_PORT must be between 1 and 65535")
    ThreadingHTTPServer((host, port), MetricsHandler).serve_forever()


if __name__ == "__main__":
    main()
