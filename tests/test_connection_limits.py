import asyncio
import base64
import unittest

from hopline.gateway import Gateway


class ConnectionLimitTests(unittest.TestCase):
    def test_second_connection_gets_503_until_first_releases(self) -> None:
        async def scenario() -> None:
            connected = asyncio.Event()
            release = asyncio.Event()

            async def upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                try:
                    await reader.readuntil(b"\r\n\r\n")
                    writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    await writer.drain()
                    connected.set()
                    await release.wait()
                finally:
                    writer.close()
                    await writer.wait_closed()

            upstream_server = await asyncio.start_server(upstream, "127.0.0.1", 0)
            upstream_port = upstream_server.sockets[0].getsockname()[1]
            gateway = Gateway(
                host="127.0.0.1", port=0, generation_port=upstream_port,
                generation_credentials={"node-a": "x"}, max_active_connections=1,
                proxy_password="x",
            )
            await gateway.start()
            token = base64.b64encode(b"hopline:x").decode()
            first_reader, first_writer = await asyncio.open_connection("127.0.0.1", gateway.port)
            first_writer.write(f"CONNECT origin.test:443 HTTP/1.1\r\nProxy-Authorization: Basic {token}\r\n\r\n".encode())
            await first_writer.drain()
            self.assertTrue((await asyncio.wait_for(first_reader.readuntil(b"\r\n\r\n"), 2)).startswith(b"HTTP/1.1 200"))
            await asyncio.wait_for(connected.wait(), 2)

            second_reader, second_writer = await asyncio.open_connection("127.0.0.1", gateway.port)
            second_writer.write(f"CONNECT origin.test:443 HTTP/1.1\r\nProxy-Authorization: Basic {token}\r\n\r\n".encode())
            await second_writer.drain()
            second_response = await asyncio.wait_for(second_reader.readuntil(b"\r\n\r\n"), 2)
            self.assertTrue(second_response.startswith(b"HTTP/1.1 503"))
            second_writer.close()
            await second_writer.wait_closed()

            release.set()
            first_writer.close()
            await first_writer.wait_closed()
            await gateway.stop()
            await gateway.wait_closed()
            upstream_server.close()
            await upstream_server.wait_closed()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
