import asyncio
import json
import unittest

from hopline.metrics import MetricsServer
from hopline.models import Node
from hopline.registry import SQLiteRegistry


class MetricsTests(unittest.TestCase):
    def test_render_uses_bounded_labels_without_credentials(self) -> None:
        registry = SQLiteRegistry(":memory:")
        registry.replace_subscription("fixture", "hash", [Node("node-a", "vless", "edge.test", 443, "secret")])
        body = MetricsServer(registry, probe_enabled=True).render().decode()
        self.assertIn('hopline_nodes 1', body)
        self.assertIn('hopline_active_probe_enabled 1', body)
        self.assertNotIn("secret", body)
        self.assertNotIn("edge.test", body)
        registry.close()

    def test_metrics_endpoint_serves_prometheus_text(self) -> None:
        async def scenario() -> None:
            registry = SQLiteRegistry(":memory:")
            server = MetricsServer(registry, port=0)
            await server.start()
            reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
            writer.write(b"GET /metrics HTTP/1.1\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            response = await reader.read()
            self.assertIn(b"HTTP/1.1 200 OK", response)
            self.assertIn(b"# TYPE hopline_nodes gauge", response)
            writer.close()
            await writer.wait_closed()
            await server.stop()
            registry.close()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
