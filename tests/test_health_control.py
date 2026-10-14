import asyncio
import json
import unittest

from hopline.control import ControlServer
from hopline.health import HealthChecker, HealthState
from hopline.models import Node
from hopline.registry import SQLiteRegistry


class HealthControlTests(unittest.TestCase):
    def test_passive_failures_transition_to_dead(self) -> None:
        registry = SQLiteRegistry(":memory:")
        registry.replace_subscription("fixture", "hash", [Node("a", "vless", "a.test", 443, "uuid")])
        checker = HealthChecker(registry)
        checker.record_failure("a", "timeout")
        self.assertEqual(registry.health_record("a").state, HealthState.DEGRADED)
        checker.record_failure("a", "timeout")
        checker.record_failure("a", "timeout")
        self.assertEqual(registry.health_record("a").state, HealthState.DEAD)

    def test_active_probe_success_records_latency(self) -> None:
        registry = SQLiteRegistry(":memory:")
        registry.replace_subscription("fixture", "hash", [Node("a", "vless", "a.test", 443, "uuid")])
        checker = HealthChecker(registry, probe=lambda node: True)
        record = asyncio.run(checker.probe_node(registry.list_nodes()[0]))
        self.assertEqual(record.state, HealthState.HEALTHY)
        self.assertIsNotNone(record.latency_ms)

    def test_failure_cooldown_excludes_node_until_clock_advances(self) -> None:
        registry = SQLiteRegistry(":memory:")
        registry.replace_subscription("fixture", "hash", [Node("a", "vless", "a.test", 443, "uuid")])
        now = [100.0]
        checker = HealthChecker(registry, clock=lambda: now[0])

        record = checker.record_failure("a", "timeout")
        self.assertEqual(record.state, HealthState.DEGRADED)
        self.assertFalse(checker.is_available("a"))
        now[0] += 30.1
        self.assertTrue(checker.is_available("a"))

    def test_dead_node_uses_backoff_and_recovers_with_hysteresis(self) -> None:
        registry = SQLiteRegistry(":memory:")
        registry.replace_subscription("fixture", "hash", [Node("a", "vless", "a.test", 443, "uuid")])
        now = [100.0]
        checker = HealthChecker(registry, clock=lambda: now[0])

        checker.record_failure("a", "timeout")
        checker.record_failure("a", "timeout")
        record = checker.record_failure("a", "timeout")
        self.assertEqual(record.state, HealthState.DEAD)
        self.assertFalse(checker.should_probe("a"))
        now[0] += 60.1
        self.assertTrue(checker.should_probe("a"))
        self.assertEqual(checker.record_success("a").state, HealthState.DEGRADED)
        self.assertEqual(checker.record_success("a").state, HealthState.DEGRADED)
        self.assertEqual(checker.record_success("a").state, HealthState.HEALTHY)

    def test_control_api_returns_nodes_without_credentials(self) -> None:
        async def scenario() -> None:
            registry = SQLiteRegistry(":memory:")
            registry.replace_subscription("fixture", "hash", [Node("a", "vless", "a.test", 443, "secret-uuid")])
            server = ControlServer(registry, port=0)
            await server.start()
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
                writer.write(b"GET /nodes HTTP/1.1\r\nHost: localhost\r\n\r\n")
                await writer.drain()
                response = await reader.read()
                body = response.split(b"\r\n\r\n", 1)[1]
                payload = json.loads(body)
                self.assertEqual(payload["nodes"][0]["health"], "unknown")
                self.assertNotIn("secret-uuid", body.decode())
                writer.close()
                await writer.wait_closed()
            finally:
                await server.stop()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
