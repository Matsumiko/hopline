import asyncio
import base64
import unittest

from hopline.models import Node
from hopline.probe import ProbeTarget, http_connect_probe


class HttpProbeTests(unittest.TestCase):
    def test_http_probe_connects_with_node_auth_and_validates_2xx(self) -> None:
        async def scenario() -> None:
            observed: list[bytes] = []

            async def proxy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                try:
                    connect = await reader.readuntil(b"\r\n\r\n")
                    observed.append(connect)
                    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    await writer.drain()
                    observed.append(await reader.readuntil(b"\r\n\r\n"))
                    writer.write(b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n")
                    await writer.drain()
                finally:
                    writer.close()
                    await writer.wait_closed()

            server = await asyncio.start_server(proxy, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            node = Node("node-a", "vless", "edge.test", 443, "secret")
            result = await http_connect_probe(node, ProbeTarget("http://provider.test/health"), proxy_port=port)
            self.assertTrue(result)
            self.assertIn(base64.b64encode(b"node-a:secret"), observed[0])
            self.assertIn(b"GET /health HTTP/1.1", observed[1])
            server.close()
            await server.wait_closed()

        asyncio.run(scenario())

    def test_http_probe_accepts_completed_non_2xx_target_response(self) -> None:
        async def scenario() -> None:
            async def proxy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                try:
                    await reader.readuntil(b"\r\n\r\n")
                    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    await writer.drain()
                    await reader.readuntil(b"\r\n\r\n")
                    writer.write(b"HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\n\r\n")
                    await writer.drain()
                finally:
                    writer.close()
                    await writer.wait_closed()

            server = await asyncio.start_server(proxy, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            result = await http_connect_probe(Node("node-a", "vless", "edge.test", 443, "secret"), ProbeTarget("http://provider.test/health"), proxy_port=port)
            self.assertTrue(result)
            server.close()
            await server.wait_closed()

        asyncio.run(scenario())

    def test_http_probe_rejects_upstream_connect_failure(self) -> None:
        async def scenario() -> None:
            async def proxy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                try:
                    await reader.readuntil(b"\r\n\r\n")
                    writer.write(b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")
                    await writer.drain()
                finally:
                    writer.close()
                    await writer.wait_closed()

            server = await asyncio.start_server(proxy, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            result = await http_connect_probe(Node("node-a", "vless", "edge.test", 443, "secret"), ProbeTarget("http://provider.test/health"), proxy_port=port)
            self.assertFalse(result)
            server.close()
            await server.wait_closed()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
