import asyncio
import unittest

from hopline.gateway import Gateway
from hopline.generation import Generation, GenerationManager


async def serve_proxy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


class GenerationGatewayTests(unittest.TestCase):
    def test_generation_manager_drains_old_generation(self) -> None:
        async def scenario() -> None:
            manager = GenerationManager()
            old = Generation(label="old", port=1)
            new = Generation(label="new", port=2)
            manager.publish(old)
            lease = manager.acquire()
            manager.publish(new)

            self.assertIs(manager.active, new)
            self.assertTrue(old.accepting is False)
            self.assertEqual(old.active_connections, 1)
            await manager.release(lease)
            await manager.wait_drained(old)
            self.assertEqual(old.active_connections, 0)

        asyncio.run(scenario())

    def test_gateway_preserves_active_relay_after_listener_stop(self) -> None:
        async def scenario() -> None:
            upstream = await asyncio.start_server(serve_proxy, "127.0.0.1", 0)
            upstream_port = upstream.sockets[0].getsockname()[1]
            gateway = Gateway(
                host="127.0.0.1",
                port=0,
                generation_port=upstream_port,
                generation_credentials={"node-a": "x"},
                proxy_password="x",
            )
            await gateway.start()
            gateway_port = gateway.port
            self.assertIsNotNone(gateway_port)

            reader, writer = await asyncio.open_connection("127.0.0.1", gateway_port)
            writer.write(
                b"CONNECT example.test:443 HTTP/1.1\r\n"
                b"Host: example.test:443\r\n"
                    b"Proxy-Authorization: Basic aG9wbGluZTp4\r\n\r\n"
            )
            await writer.drain()
            self.assertEqual(
                await reader.readuntil(b"\r\n\r\n"),
                b"HTTP/1.1 200 Connection Established\r\n\r\n",
            )

            writer.write(b"post-body")
            await asyncio.wait_for(writer.drain(), 2)
            self.assertEqual(
                await asyncio.wait_for(reader.readexactly(9), 2), b"post-body"
            )

            await gateway.stop()
            writer.write(b"still-active")
            await asyncio.wait_for(writer.drain(), 2)
            self.assertEqual(
                await asyncio.wait_for(reader.readexactly(12), 2), b"still-active"
            )
            writer.close()
            await writer.wait_closed()
            await gateway.wait_closed()
            upstream.close()
            await upstream.wait_closed()

        asyncio.run(scenario())
    def test_long_stream_is_relayed_incrementally(self) -> None:
        async def scenario() -> None:
            first_chunk = b"chunk-1"
            second_chunk = b"chunk-2"
            sent = asyncio.Event()

            async def streaming_proxy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                try:
                    await reader.readuntil(b"\r\n\r\n")
                    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    await writer.drain()
                    writer.write(first_chunk)
                    await writer.drain()
                    sent.set()
                    await asyncio.sleep(0.05)
                    writer.write(second_chunk)
                    await writer.drain()
                    await asyncio.sleep(0.05)
                finally:
                    writer.close()
                    await writer.wait_closed()

            upstream = await asyncio.start_server(streaming_proxy, "127.0.0.1", 0)
            gateway = Gateway(
                host="127.0.0.1", port=0,
                generation_port=upstream.sockets[0].getsockname()[1],
                generation_credentials={"node-a": "x"}, proxy_password="x",
            )
            await gateway.start()
            reader, writer = await asyncio.open_connection("127.0.0.1", gateway.port)
            writer.write(b"CONNECT example.test:443 HTTP/1.1\r\nProxy-Authorization: Basic aG9wbGluZTp4\r\n\r\n")
            await writer.drain()
            self.assertEqual(await reader.readuntil(b"\r\n\r\n"), b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await asyncio.wait_for(sent.wait(), 2)
            self.assertEqual(await asyncio.wait_for(reader.readexactly(len(first_chunk)), 2), first_chunk)
            self.assertEqual(await asyncio.wait_for(reader.readexactly(len(second_chunk)), 2), second_chunk)
            writer.close()
            await writer.wait_closed()
            await gateway.stop()
            await gateway.wait_closed()
            upstream.close()
            await upstream.wait_closed()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
