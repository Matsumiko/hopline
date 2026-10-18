import unittest
import asyncio
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

from hopline.geolocation import GeoResult
from hopline.cli import _geo, _geo_all
from hopline.health import HealthState
from hopline.models import Node
from hopline.registry import SQLiteRegistry
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

    def test_scheduler_does_not_retire_sources_after_partial_cycle(self) -> None:
        syncer = type("FakeSyncer", (), {})()
        syncer.registry = type("FakeRegistry", (), {
            "reconcile_subscription_sources": lambda self, sources: (_ for _ in ()).throw(AssertionError("partial cycle retired sources")),
            "list_removed_subscriptions": lambda self: [],
            "list_managed_subscriptions": lambda self: [],
        })()
        syncer.sync_url = AsyncMock(side_effect=lambda source: (scheduler.stop(), SyncResult(source, True, 1, 0, False))[1])
        scheduler = SubscriptionScheduler(syncer, ["one", "two"], interval=10, jitter=0)

        results = asyncio.run(scheduler.sync_once())

        self.assertEqual([result.source for result in results], ["one"])
        scheduler.stop()

    def test_geo_all_refreshes_missing_nodes_and_skips_dead_and_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "registry.db"
            config_path = Path(directory) / "hopline.toml"
            config_path.write_text(
                f'static_nodes = ["vless://00000000-0000-4000-8000-000000000099@example.test:443"]\n\n[hopline]\ndatabase = "{database}"\ncountry_max_age = 3600\n\n[auth]\npassword = "local-secret"\n',
                encoding="utf-8",
            )
            config_path.chmod(0o600)
            registry = SQLiteRegistry(str(database))
            registry.replace_subscription(
                "fixture",
                "hash",
                [
                    Node("fresh", "vless", "fresh.test", 443, "secret-fresh"),
                    Node("missing", "vless", "missing.test", 443, "secret-missing"),
                    Node("dead", "vless", "dead.test", 443, "secret-dead"),
                ],
            )
            registry.save_health("fresh", HealthState.HEALTHY, 1, 0, 10.0, None)
            registry.save_health("missing", HealthState.HEALTHY, 1, 0, 10.0, None)
            registry.save_health("dead", HealthState.DEAD, 3, 3, None, "timeout")
            from hopline.geolocation import GeoResult
            registry.save_geolocation("fresh", GeoResult("203.0.113.1", "ID", "Indonesia", None, None, "fixture", time.time()))
            registry.close()

            async def resolve(_config, _registry, node_id, _url, _resolver):
                return {"node": node_id, "country_code": "US"}

            with patch("hopline.cli._resolve_geo_node", new=resolve):
                payload = asyncio.run(_geo_all(str(config_path), "https://api.example.test/ip", 2))

            self.assertEqual(payload["selected"], 1)
            self.assertEqual(payload["updated"], 1)
            self.assertEqual(payload["countries"], {"US": 1})
            self.assertEqual(payload["skipped"], {"fresh": 1, "dead": 1, "quarantine": 0})

    def test_geo_all_queues_all_missing_nodes_with_bounded_concurrency(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "registry.db"
            config_path = Path(directory) / "hopline.toml"
            config_path.write_text(
                f'static_nodes = ["vless://00000000-0000-4000-8000-000000000199@example.test:443"]\n\n[hopline]\ndatabase = "{database}"\ncountry_max_age = 3600\n\n[auth]\npassword = "local-secret"\n',
                encoding="utf-8",
            )
            config_path.chmod(0o600)
            registry = SQLiteRegistry(str(database))
            registry.replace_subscription(
                "fixture",
                "hash",
                [Node(str(index), "vless", "edge.test", 443, f"secret-{index}") for index in range(4)],
            )
            for index in range(4):
                registry.save_health(str(index), HealthState.HEALTHY, 1, 0, 10.0, None)
            registry.close()
            active = 0
            maximum = 0

            async def resolve(_config, _registry, node_id, _url, _resolver):
                nonlocal active, maximum
                active += 1
                maximum = max(maximum, active)
                await asyncio.sleep(0.01)
                active -= 1
                return {"node": node_id, "country_code": "US"}

            with patch("hopline.cli._resolve_geo_node", new=resolve):
                payload = asyncio.run(_geo_all(str(config_path), "https://api.example.test/ip", 2))

            self.assertEqual(payload["selected"], 4)
            self.assertEqual(payload["updated"], 4)
            self.assertEqual(payload["countries"], {"US": 4})
            self.assertEqual(maximum, 2)

    def test_geo_command_fetches_exit_ip_resolves_and_persists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "registry.db"
            config_path = Path(directory) / "hopline.toml"
            config_path.write_text(
                f'static_nodes = ["vless://00000000-0000-4000-8000-000000000001@example.test:443"]\n\n[hopline]\ndatabase = "{database}"\n\n[auth]\npassword = "local-secret"\n',
                encoding="utf-8",
            )
            config_path.chmod(0o600)
            registry = SQLiteRegistry(str(database))
            registry.replace_subscription("fixture", "hash", [Node("node-a", "vless", "relay.test", 443, "node-secret")])
            registry.close()
            geo_result = GeoResult("203.0.113.8", "ID", "Indonesia", "AS64500", "Example", "checkip", 10.0)
            resolver = type("FakeResolver", (), {"resolve": lambda self, ip: geo_result})
            with patch("hopline.cli.fetch_exit_ip", return_value="203.0.113.8") as fetch_ip, patch(
                "hopline.cli.GeolocationResolver", return_value=resolver()
            ):
                payload = asyncio.run(_geo(str(config_path), "node-a", "https://api.example.test/ip"))
            fetch_ip.assert_called_once()
            self.assertEqual(payload["country_code"], "ID")
            saved = SQLiteRegistry(str(database)).geolocation_record("node-a")
            self.assertEqual(saved["ip"], "203.0.113.8")
            self.assertNotIn("node-secret", json.dumps(payload))

    def test_cli_help_is_available_without_database_or_url(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "hopline", "--help"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("sync", result.stdout)
        self.assertIn("geo", result.stdout)
        self.assertIn("doctor", result.stdout)

    def test_cli_geo_requires_config_and_node(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "hopline", "geo", "--node", "node-a", "--json"],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("config file does not exist", result.stderr)

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
        self.assertEqual(payload["schema_version"], 2)
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
