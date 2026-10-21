import asyncio
import stat
import tempfile
import unittest
from pathlib import Path

from hopline.config import HoplineConfig
from hopline.health import HealthChecker, HealthState
from hopline.models import Node
from hopline.probe import ActiveProbeScheduler, ProbeTarget
from hopline.registry import SQLiteRegistry


class ProbeTests(unittest.TestCase):
    def test_config_reads_probe_targets_without_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "hopline.toml"
            path.write_text(
                '[hopline]\ndatabase = "registry.db"\n\n[auth]\npassword = "fixture-local-password"\n\n[[subscriptions]]\nurl = "https://example.test/sub"\n\n[health]\ntargets = ["https://provider.test/health"]\ninterval = 60\ntimeout = 5\n',
                encoding="utf-8",
            )
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            config = HoplineConfig.from_file(path)
            self.assertEqual(config.probe_targets, ("https://provider.test/health",))
            self.assertEqual(config.probe_interval, 60)
            self.assertEqual(config.probe_timeout, 5)

    def test_probe_records_failure_and_success(self) -> None:
        async def scenario() -> None:
            registry = SQLiteRegistry(":memory:")
            node = Node("a", "vless", "edge.test", 443, "secret")
            registry.replace_subscription("fixture", "hash", [node])
            calls = 0

            async def probe(_node: Node, _target: ProbeTarget) -> bool:
                nonlocal calls
                calls += 1
                return calls > 1

            scheduler = ActiveProbeScheduler(
                HealthChecker(registry), registry.list_nodes, ["https://provider.test/health"],
                interval=10, timeout=1, probe=probe,
            )
            first = await scheduler.probe_once()
            self.assertEqual(first[0].state, HealthState.DEGRADED)
            second = await scheduler.probe_once()
            self.assertEqual(second[0].state, HealthState.DEGRADED)
            third = await scheduler.probe_once()
            self.assertEqual(third[0].state, HealthState.DEGRADED)
            fourth = await scheduler.probe_once()
            self.assertEqual(fourth[0].state, HealthState.HEALTHY)
            registry.close()

        asyncio.run(scenario())

    def test_probe_timeout_marks_node_degraded(self) -> None:
        async def scenario() -> None:
            registry = SQLiteRegistry(":memory:")
            node = Node("a", "vless", "edge.test", 443, "secret")
            registry.replace_subscription("fixture", "hash", [node])

            async def probe(_node: Node, _target: ProbeTarget) -> bool:
                await asyncio.sleep(1)
                return True

            scheduler = ActiveProbeScheduler(
                HealthChecker(registry), registry.list_nodes, ["https://provider.test/health"],
                interval=10, timeout=0.01, probe=probe,
            )
            record = (await scheduler.probe_once())[0]
            self.assertEqual(record.state, HealthState.DEGRADED)
            self.assertEqual(record.failure_category, "connect_timeout")
            registry.close()

        asyncio.run(scenario())
    def test_probe_queue_limits_concurrency_and_records_new_nodes(self) -> None:
        async def scenario() -> None:
            registry = SQLiteRegistry(":memory:")
            nodes = [Node(str(index), "vless", "edge.test", 443, f"secret-{index}") for index in range(8)]
            registry.replace_subscription("fixture", "hash", nodes)
            active = 0
            maximum = 0

            async def probe(_node: Node, _target: ProbeTarget) -> bool:
                nonlocal active, maximum
                active += 1
                maximum = max(maximum, active)
                await asyncio.sleep(0.01)
                active -= 1
                return True

            scheduler = ActiveProbeScheduler(
                HealthChecker(registry), registry.list_nodes, ["https://provider.test/health"],
                interval=10, timeout=1, concurrency=3, probe=probe,
            )
            records = await scheduler.probe_once()
            self.assertEqual(len(records), len(nodes))
            self.assertEqual(maximum, 3)
            self.assertEqual(len(registry.list_health()), len(nodes))
            self.assertTrue(all(record.state == HealthState.HEALTHY for record in records))
            registry.close()

        asyncio.run(scenario())

    def test_probe_run_stops_cleanly(self) -> None:
        async def scenario() -> None:
            registry = SQLiteRegistry(":memory:")
            node = Node("a", "vless", "edge.test", 443, "secret")
            registry.replace_subscription("fixture", "hash", [node])
            started = asyncio.Event()

            async def probe(_node: Node, _target: ProbeTarget) -> bool:
                started.set()
                return True

            scheduler = ActiveProbeScheduler(
                HealthChecker(registry), registry.list_nodes, ["https://provider.test/health"],
                interval=60, timeout=1, probe=probe,
            )
            task = asyncio.create_task(scheduler.run())
            await asyncio.wait_for(started.wait(), 1)
            scheduler.stop()
            await asyncio.wait_for(task, 1)
            registry.close()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
