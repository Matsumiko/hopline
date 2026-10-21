import asyncio
import unittest

from hopline.failures import (
    AUTH_REJECTED,
    CONNECT_REFUSED,
    CONNECT_TIMEOUT,
    FailureReason,
    classify_exception,
    parse_legacy,
    redact,
)
from hopline.health import HealthChecker, HealthState
from hopline.metrics import MetricsServer
from hopline.models import Node
from hopline.registry import SQLiteRegistry


class StructuredFailureTests(unittest.TestCase):
    def test_redaction_strips_credentials_and_share_links(self) -> None:
        samples = [
            "Proxy-Authorization: Basic aG9wbGluZTpzZWNyZXQ=",
            "vless://00000000-0000-4000-8000-000000000001@edge.test:443?security=tls#node",
            "password=hunter2",
            "token: abcdef123456",
        ]
        for sample in samples:
            cleaned = redact(sample)
            self.assertIn("[redacted]", cleaned)
            for secret in ("aG9wbGluZTpzZWNyZXQ=", "00000000-0000-4000-8000-000000000001", "hunter2", "abcdef123456"):
                self.assertNotIn(secret, cleaned)

    def test_failure_reason_normalizes_unknown_category(self) -> None:
        reason = FailureReason("made_up", "detail")
        self.assertEqual(reason.category, "unknown")
        self.assertEqual(reason.detail, "detail")

    def test_classify_exception_maps_common_errors(self) -> None:
        self.assertEqual(classify_exception(asyncio.TimeoutError()).category, CONNECT_TIMEOUT)
        self.assertEqual(classify_exception(ConnectionRefusedError()).category, CONNECT_REFUSED)

    def test_legacy_error_strings_are_migrated(self) -> None:
        self.assertEqual(parse_legacy("TimeoutError").category, CONNECT_TIMEOUT)
        self.assertEqual(parse_legacy("upstream_rejected").category, "upstream_rejected")
        self.assertEqual(parse_legacy("ConnectionRefusedError").category, CONNECT_REFUSED)
        self.assertIsNone(parse_legacy(None))

    def test_failure_code_never_contains_secret(self) -> None:
        reason = FailureReason(AUTH_REJECTED, "password=hunter2 vless://uuid@host:443")
        self.assertNotIn("hunter2", reason.code)
        self.assertNotIn("uuid@host", reason.code)


class HealthPerformanceSeparationTests(unittest.TestCase):
    def _registry(self) -> SQLiteRegistry:
        registry = SQLiteRegistry(":memory:")
        registry.replace_subscription("fixture", "hash", [Node("a", "vless", "a.test", 443, "secret")])
        return registry

    def test_connection_failures_do_not_change_health_state(self) -> None:
        registry = self._registry()
        checker = HealthChecker(registry)
        checker.record_success("a")
        self.assertEqual(registry.health_record("a").state, HealthState.HEALTHY)

        for _ in range(5):
            checker.record_connection("a", ok=False, reason=FailureReason(CONNECT_TIMEOUT))

        record = registry.health_record("a")
        self.assertEqual(record.state, HealthState.HEALTHY, "relay failure must not poison probe health")
        self.assertEqual(record.conn_failures, 5)
        self.assertEqual(record.failure_category, CONNECT_TIMEOUT)
        registry.close()

    def test_probe_updates_preserve_connection_performance(self) -> None:
        registry = self._registry()
        checker = HealthChecker(registry)
        checker.record_success("a")
        checker.record_connection("a", ok=True, latency_ms=100.0)
        checker.record_connection("a", ok=False, reason=FailureReason(CONNECT_TIMEOUT))

        record = checker.record_failure("a", FailureReason(CONNECT_REFUSED))
        self.assertEqual(record.conn_successes, 1)
        self.assertEqual(record.conn_failures, 1)
        self.assertIsNotNone(record.latency_ewma_ms)
        self.assertEqual(record.failure_category, CONNECT_REFUSED)
        registry.close()

    def test_ewma_tracks_recent_latency(self) -> None:
        registry = self._registry()
        checker = HealthChecker(registry)
        checker.record_success("a")
        checker.record_connection("a", ok=True, latency_ms=100.0)
        record = checker.record_connection("a", ok=True, latency_ms=200.0)
        self.assertEqual(record.latency_ewma_ms, 120.0)
        registry.close()

    def test_metrics_expose_protocol_success_rate_and_resources(self) -> None:
        registry = self._registry()
        registry.replace_subscription(
            "other", "hash", [Node("b", "trojan", "b.test", 443, "secret-b")]
        )
        checker = HealthChecker(registry)
        checker.record_success("a")
        checker.record_success("b")
        checker.record_connection("a", ok=True, latency_ms=50.0)
        checker.record_connection("a", ok=False, reason=FailureReason(CONNECT_TIMEOUT))
        checker.record_connection("b", ok=True, latency_ms=80.0)

        body = MetricsServer(registry).render().decode()
        self.assertIn('hopline_protocol_connection_total{protocol="vless",outcome="success"} 1', body)
        self.assertIn('hopline_protocol_connection_total{protocol="vless",outcome="failure"} 1', body)
        self.assertIn('hopline_protocol_connection_total{protocol="trojan",outcome="success"} 1', body)
        self.assertIn('hopline_protocol_probe_total{protocol="vless",outcome="success"} 1', body)
        self.assertIn('hopline_protocol_latency_ewma_ms{protocol="vless"}', body)
        self.assertIn('hopline_failure_nodes{category="connect_timeout"} 1', body)
        self.assertIn("hopline_process_cpu_seconds_total", body)
        self.assertIn("hopline_process_resident_memory_bytes", body)
        # No credentials, hosts, or node IDs may appear in metrics.
        for forbidden in ("secret", "a.test", "b.test", '"a"', '"b"'):
            self.assertNotIn(forbidden, body)
        registry.close()


if __name__ == "__main__":
    unittest.main()
