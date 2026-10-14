import asyncio
import base64
import unittest

from hopline.gateway import Gateway
from hopline.health import HealthState
from hopline.sticky import StickySessionStore


class GatewayStickyTests(unittest.TestCase):
    def test_same_sticky_session_reuses_node(self) -> None:
        async def scenario() -> None:
            received: list[str] = []

            async def proxy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                try:
                    raw = await reader.readuntil(b"\r\n\r\n")
                    token = raw.split(b"Proxy-Authorization: Basic ", 1)[1].split(b"\r\n", 1)[0]
                    node_id = base64.b64decode(token).decode().split(":", 1)[0]
                    received.append(node_id)
                    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    await writer.drain()
                    writer.write(node_id.encode())
                    await writer.drain()
                finally:
                    writer.close()
                    await writer.wait_closed()

            upstream = await asyncio.start_server(proxy, "127.0.0.1", 0)
            gateway = Gateway(
                host="127.0.0.1", port=0,
                generation_port=upstream.sockets[0].getsockname()[1],
                generation_credentials={"node-a": "x", "node-b": "x"},
                proxy_password="x",
            )
            await gateway.start()
            try:
                for _ in range(2):
                    reader, writer = await asyncio.open_connection("127.0.0.1", gateway.port)
                    token = base64.b64encode(b"sticky-job-42:x").decode()
                    writer.write(f"CONNECT target.test:443 HTTP/1.1\r\nProxy-Authorization: Basic {token}\r\n\r\n".encode())
                    await writer.drain()
                    await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
                    await asyncio.wait_for(reader.readexactly(6), 2)
                    writer.close()
                    await writer.wait_closed()
                self.assertEqual(received, ["node-a", "node-a"])
            finally:
                await gateway.stop()
                await gateway.wait_closed()
                upstream.close()
                await upstream.wait_closed()

        asyncio.run(scenario())

    def test_sticky_rebinds_when_bound_node_becomes_unavailable(self) -> None:
        async def scenario() -> None:
            received: list[str] = []
            states = {"node-a": HealthState.HEALTHY, "node-b": HealthState.HEALTHY}

            async def proxy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                try:
                    raw = await reader.readuntil(b"\r\n\r\n")
                    token = raw.split(b"Proxy-Authorization: Basic ", 1)[1].split(b"\r\n", 1)[0]
                    node_id = base64.b64decode(token).decode().split(":", 1)[0]
                    received.append(node_id)
                    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    await writer.drain()
                    writer.write(node_id.encode())
                    await writer.drain()
                finally:
                    writer.close()
                    await writer.wait_closed()

            upstream = await asyncio.start_server(proxy, "127.0.0.1", 0)
            gateway = Gateway(
                host="127.0.0.1", port=0,
                generation_port=upstream.sockets[0].getsockname()[1],
                generation_credentials={"node-a": "x", "node-b": "x"},
                health_state=states.get,
                proxy_password="x",
            )
            await gateway.start()
            try:
                async def request() -> None:
                    reader, writer = await asyncio.open_connection("127.0.0.1", gateway.port)
                    token = base64.b64encode(b"sticky-job-42:x").decode()
                    writer.write(f"CONNECT target.test:443 HTTP/1.1\r\nProxy-Authorization: Basic {token}\r\n\r\n".encode())
                    await writer.drain()
                    await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
                    await asyncio.wait_for(reader.readexactly(6), 2)
                    writer.close()
                    await writer.wait_closed()

                await request()
                states["node-a"] = HealthState.DEAD
                await request()
                self.assertEqual(received, ["node-a", "node-b"])
            finally:
                await gateway.stop()
                await gateway.wait_closed()
                upstream.close()
                await upstream.wait_closed()

        asyncio.run(scenario())

    def test_sticky_returns_503_when_no_node_is_eligible(self) -> None:
        async def scenario() -> None:
            async def proxy(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                writer.close()
                await writer.wait_closed()

            upstream = await asyncio.start_server(proxy, "127.0.0.1", 0)
            states = {"node-a": HealthState.DEAD}
            gateway = Gateway(
                host="127.0.0.1", port=0,
                generation_port=upstream.sockets[0].getsockname()[1],
                generation_credentials={"node-a": "x"},
                health_state=states.get,
                proxy_password="x",
            )
            await gateway.start()
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", gateway.port)
                token = base64.b64encode(b"sticky-job-42:x").decode()
                writer.write(f"CONNECT target.test:443 HTTP/1.1\r\nProxy-Authorization: Basic {token}\r\n\r\n".encode())
                await writer.drain()
                response = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
                self.assertTrue(response.startswith(b"HTTP/1.1 503"))
                writer.close()
                await writer.wait_closed()
            finally:
                await gateway.stop()
                await gateway.wait_closed()
                upstream.close()
                await upstream.wait_closed()

        asyncio.run(scenario())

    def test_gateway_sticky_ttl_is_configurable(self) -> None:
        store = StickySessionStore(ttl=5, clock=lambda: 10.0)
        self.assertEqual(store.ttl, 5)


if __name__ == "__main__":
    unittest.main()
