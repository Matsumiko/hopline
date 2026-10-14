import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

from hopline.scheduler import SubscriptionScheduler
from hopline.syncer import SyncResult


class SchedulerCliTests(unittest.TestCase):
    def test_scheduler_syncs_each_source_and_stops_before_next_cycle(self) -> None:
        syncer = type("FakeSyncer", (), {})()
        syncer.sync_url = AsyncMock(
            side_effect=[
                SyncResult("one", True, 1, 0, False),
                SyncResult("two", False, 1, 0, False),
            ]
        )
        scheduler = SubscriptionScheduler(syncer, ["one", "two"], interval=10, jitter=0)

        results = asyncio.run(scheduler.sync_once())

        self.assertEqual([result.source for result in results], ["one", "two"])
        self.assertEqual(syncer.sync_url.await_count, 2)
        scheduler.stop()

    def test_cli_help_is_available_without_database_or_url(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "hopline", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("sync", result.stdout)
        self.assertIn("doctor", result.stdout)

    def test_cli_doctor_json_is_parseable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "registry.db")
            result = subprocess.run(
                [sys.executable, "-m", "hopline", "doctor", "--db", database, "--json"],
                capture_output=True,
                text=True,
                check=False,
            )
        self.assertIn(result.returncode, {0, 2})
        payload = json.loads(result.stdout)
        self.assertEqual(payload["schema_version"], 1)
        self.assertEqual(payload["nodes"], 0)
        self.assertNotIn("password", result.stdout.lower())

    def test_cli_sync_requires_url_on_stderr(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "hopline", "sync", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("subscription URL is required", result.stderr)


if __name__ == "__main__":
    unittest.main()
