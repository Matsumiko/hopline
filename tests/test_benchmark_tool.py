import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


class BenchmarkToolTests(unittest.TestCase):
    def test_benchmark_invariants(self) -> None:
        root = Path(__file__).resolve().parent.parent
        env = dict(os.environ, PYTHONPATH=str(root))
        result = subprocess.run(
            [sys.executable, "tools/benchmark.py", "--rounds", "1", "--json"],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)
        admission = report["admission"]["raw"][0]
        self.assertEqual(admission["accepted"], admission["limit_per_node"])
        self.assertEqual(admission["admitted"], admission["limit_per_node"])
        self.assertEqual(
            admission["accepted"] + admission["rejected"], admission["concurrency"]
        )
        swap = report["generation_swap"]["raw"][0]
        self.assertEqual(
            swap["streams_alive_after_swap"],
            swap["connections"],
            "generation swap must not drop active streams",
        )
        relay = report["relay_throughput"]["raw"][0]
        self.assertEqual(relay["received_bytes"], relay["bytes"])


if __name__ == "__main__":
    unittest.main()
