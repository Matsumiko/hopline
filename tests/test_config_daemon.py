import asyncio
import contextlib
import io
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from hopline.config import HoplineConfig
from hopline.cli import _run_daemon
from hopline.registry import SQLiteRegistry
from hopline.syncer import SyncResult


class ConfigDaemonTests(unittest.TestCase):
    def test_config_requires_private_file_and_reads_sources(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hopline.toml"
            path.write_text(
                '[hopline]\ndatabase = "registry.db"\ninterval = 60\njitter = 5\n\n[[subscriptions]]\nurl = "https://example.test/sub"\n',
                encoding="utf-8",
            )
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            config = HoplineConfig.from_file(path)
            self.assertEqual(config.database, "registry.db")
            self.assertEqual(config.subscriptions, ("https://example.test/sub",))
            self.assertEqual(config.interval, 60)
            self.assertEqual(config.jitter, 5)

    def test_config_rejects_world_readable_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hopline.toml"
            path.write_text('[hopline]\n\n[[subscriptions]]\nurl = "https://example.test/sub"\n', encoding="utf-8")
            path.chmod(stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)
            with self.assertRaises(ValueError):
                HoplineConfig.from_file(path)

    def test_run_once_closes_registry_after_sync(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "hopline.toml"
            database = Path(directory) / "registry.db"
            config_path.write_text(
                f'[hopline]\ndatabase = "{database}"\ninterval = 60\n\n[[subscriptions]]\nurl = "https://example.test/sub"\n',
                encoding="utf-8",
            )
            config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            result = SyncResult("https://example.test/sub", True, 1, 0, False)
            with patch("hopline.cli.SubscriptionScheduler.sync_once", new=AsyncMock(return_value=[result])):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(asyncio.run(_run_daemon(str(config_path), True)), 2)
            self.assertEqual(len(SQLiteRegistry(str(database)).list_nodes()), 0)


if __name__ == "__main__":
    unittest.main()
