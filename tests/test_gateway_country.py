import asyncio
import base64
import unittest

from hopline.gateway import Gateway
from hopline.health import HealthState


class GatewayCountryTests(unittest.TestCase):
    def test_country_route_uses_only_fresh_matching_nodes(self) -> None:
        async def scenario() -> None:
            received: list[str] = []
            metadata = {"node-a": ("ID", 100.0), "node-b": ("SG", 100.0)}

            async def proxy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                try:
                    raw = await reader.readuntil(b"\r\n\r\n")
                    token = raw.split(b"Proxy-Authorization: Basic ", 1)[1].split(b"\r\n", 1)[0]
                    node_id = base64.b64decode(token).decode().split(":", 1)[0]
                    received.append(node_id)
                    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n" + node_id.encode())
                    await writer.drain()
                finally:
                    writer.close()
                    await writer.wait_closed()

            upstream = await asyncio.start_server(proxy, "127.0.0.1", 0)
            gateway = Gateway(
                host="127.0.0.1", port=0,
                generation_port=upstream.sockets[0].getsockname()[1],
                generation_credentials={"node-a": "x", "node-b": "x"},
                country_metadata=metadata.get,
                country_max_age=60,
                clock=lambda: 110.0,
                proxy_password="x",
            )
            await gateway.start()
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", gateway.port)
                token = base64.b64encode(b"country-sg:x").decode()
                writer.write(f"CONNECT target.test:443 HTTP/1.1\r\nProxy-Authorization: Basic {token}\r\n\r\n".encode())
                await writer.drain()
                response = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
                self.assertTrue(response.startswith(b"HTTP/1.1 200"))
                self.assertEqual(await asyncio.wait_for(reader.readexactly(6), 2), b"node-b")
                writer.close()
                await writer.wait_closed()
                self.assertEqual(received, ["node-b"])
            finally:
                await gateway.stop()
                await gateway.wait_closed()
                upstream.close()
                await upstream.wait_closed()

        asyncio.run(scenario())

    def test_country_route_stale_metadata_returns_503(self) -> None:
        async def scenario() -> None:
            async def proxy(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                writer.close()
                await writer.wait_closed()

            upstream = await asyncio.start_server(proxy, "127.0.0.1", 0)
            gateway = Gateway(
                host="127.0.0.1", port=0,
                generation_port=upstream.sockets[0].getsockname()[1],
                generation_credentials={"node-a": "x"},
                country_metadata=lambda _node_id: ("ID", 100.0),
                country_max_age=60,
                clock=lambda: 200.0,
                proxy_password="x",
            )
            await gateway.start()
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", gateway.port)
                token = base64.b64encode(b"country-id:x").decode()
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

    def test_country_sticky_rebind_stays_in_country_pool(self) -> None:
        async def scenario() -> None:
            received: list[str] = []
            states = {"node-a": HealthState.HEALTHY, "node-b": HealthState.HEALTHY, "node-c": HealthState.HEALTHY}
            metadata = {"node-a": ("ID", 100.0), "node-b": ("ID", 100.0), "node-c": ("SG", 100.0)}

            async def proxy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                try:
                    raw = await reader.readuntil(b"\r\n\r\n")
                    token = raw.split(b"Proxy-Authorization: Basic ", 1)[1].split(b"\r\n", 1)[0]
                    node_id = base64.b64decode(token).decode().split(":", 1)[0]
                    received.append(node_id)
                    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n" + node_id.encode())
                    await writer.drain()
                finally:
                    writer.close()
                    await writer.wait_closed()

            upstream = await asyncio.start_server(proxy, "127.0.0.1", 0)
            gateway = Gateway(
                host="127.0.0.1", port=0,
                generation_port=upstream.sockets[0].getsockname()[1],
                generation_credentials={key: "x" for key in states},
                health_state=states.get,
                country_metadata=metadata.get,
                country_max_age=60,
                clock=lambda: 110.0,
                proxy_password="x",
            )
            await gateway.start()
            try:
                async def request() -> None:
                    reader, writer = await asyncio.open_connection("127.0.0.1", gateway.port)
                    token = base64.b64encode(b"country-id-sticky-job:x").decode()
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
                self.assertNotIn("node-c", received)
            finally:
                await gateway.stop()
                await gateway.wait_closed()
                upstream.close()
                await upstream.wait_closed()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
