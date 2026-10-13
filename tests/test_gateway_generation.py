import asyncio
import unittest

from hopline.gateway import Gateway


async def echo_label(label: bytes, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        while data := await reader.read(65536):
            writer.write(label + data)
            await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


class GatewayGenerationTests(unittest.TestCase):
    def test_publish_generation_does_not_rebind_existing_relay(self) -> None:
        async def scenario() -> None:
            old_server = await asyncio.start_server(
                lambda r, w: echo_label(b"old:", r, w), "127.0.0.1", 0
            )
            new_server = await asyncio.start_server(
                lambda r, w: echo_label(b"new:", r, w), "127.0.0.1", 0
            )
            old_port = old_server.sockets[0].getsockname()[1]
            new_port = new_server.sockets[0].getsockname()[1]
            gateway = Gateway(
                host="127.0.0.1",
                port=0,
                generation_port=old_port,
                generation_credentials={"node": "x"},
            )
            await gateway.start()
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", gateway.port)
                writer.write(
                    b"CONNECT target.test:443 HTTP/1.1\r\n"
                    b"Proxy-Authorization: Basic bm9kZTp4\r\n\r\n"
                )
                await writer.drain()
                await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
                gateway.publish_generation(new_port, {"node": "x"})

                writer.write(b"old-stream")
                await writer.drain()
                self.assertEqual(
                    await asyncio.wait_for(reader.readexactly(14), 2), b"old:old-stream"
                )
                writer.close()
                await writer.wait_closed()
                await gateway.stop()
                await gateway.wait_closed()
            finally:
                old_server.close()
                new_server.close()
                await old_server.wait_closed()
                await new_server.wait_closed()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
