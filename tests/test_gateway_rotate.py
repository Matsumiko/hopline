import asyncio
import base64
import unittest

from hopline.gateway import Gateway


class GatewayRotateTests(unittest.TestCase):
    def test_rotate_selects_each_node_for_new_connection(self) -> None:
        async def scenario() -> None:
            received: list[str] = []

            async def proxy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                try:
                    raw = await reader.readuntil(b"\r\n\r\n")
                    if b"bm9kZS1hOng=" in raw:
                        label = "node-a"
                    elif b"bm9kZS1iOng=" in raw:
                        label = "node-b"
                    else:
                        raise AssertionError("missing upstream node credential")
                    received.append(label)
                    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    await writer.drain()
                    writer.write(label.encode())
                    await writer.drain()
                finally:
                    writer.close()
                    await writer.wait_closed()

            upstream = await asyncio.start_server(proxy, "127.0.0.1", 0)
            upstream_port = upstream.sockets[0].getsockname()[1]
            gateway = Gateway(
                host="127.0.0.1",
                port=0,
                generation_port=upstream_port,
                generation_credentials={"node-a": "x", "node-b": "x"},
            )
            await gateway.start()
            try:
                for expected in (b"node-a", b"node-b"):
                    reader, writer = await asyncio.open_connection("127.0.0.1", gateway.port)
                    token = base64.b64encode(b"rotate:x").decode()
                    writer.write(
                        f"CONNECT target.test:443 HTTP/1.1\r\nProxy-Authorization: Basic {token}\r\n\r\n".encode()
                    )
                    await writer.drain()
                    await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
                    self.assertEqual(
                        await asyncio.wait_for(reader.readexactly(len(expected)), 2), expected
                    )
                    writer.close()
                    await writer.wait_closed()
                self.assertEqual(received, ["node-a", "node-b"])
            finally:
                await gateway.stop()
                await gateway.wait_closed()
                upstream.close()
                await upstream.wait_closed()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
