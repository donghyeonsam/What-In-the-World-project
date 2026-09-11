import importlib.util
import pathlib
import unittest
from unittest.mock import patch


MODULE_PATH = pathlib.Path(__file__).with_name("hdfs_exporter.py")
SPEC = importlib.util.spec_from_file_location("hdfs_exporter", MODULE_PATH)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


class HdfsExporterTest(unittest.TestCase):
    def test_first_numeric_uses_alias_and_converts_gib(self):
        beans = [{"CapacityUsedGB": 2}]
        self.assertEqual(
            2 * 1024**3,
            exporter._first_numeric(beans, ("CapacityUsed", "CapacityUsedGB")),
        )

    def test_collect_keeps_jmx_metrics_when_a_path_is_missing(self):
        def fake_fetch(url):
            if "/webhdfs/" in url:
                raise OSError("missing path")
            if "namenode" in url:
                return {
                    "beans": [
                        {
                            "CapacityTotal": 1000,
                            "CapacityUsed": 250,
                            "NumLiveDataNodes": 1,
                            "NumDeadDataNodes": 0,
                        }
                    ]
                }
            return {"beans": [{"Capacity": 1000, "DfsUsed": 250}]}

        with patch.object(exporter, "_fetch_json", side_effect=fake_fetch), patch.object(
            exporter, "PATHS", ("/missing",)
        ):
            metrics = exporter.collect_metrics()

        self.assertIn("hdfs_capacity_total_bytes 1000", metrics)
        self.assertIn('hdfs_exporter_path_up{path="/missing"} 0', metrics)
        self.assertIn("hdfs_exporter_scrape_success 1", metrics)


if __name__ == "__main__":
    unittest.main()
