from __future__ import annotations

import asyncio
import base64

from hopline.gateway import Gateway


async def relay(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    async def pipe(source: asyncio.StreamReader, destination: asyncio.StreamWriter) -> None:
        try:
            while data := await source.read(65536):
                destination.write(data)
                await destination.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass

    await asyncio.gather(pipe(reader, writer), pipe(reader, writer))


async def run() -> None:
    async def origin(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            payload = await reader.read(4)
            writer.write(payload)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

    origin_server = await asyncio.start_server(origin, "127.0.0.1", 0)
    origin_port = origin_server.sockets[0].getsockname()[1]

    async def tunnel_proxy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        upstream_writer: asyncio.StreamWriter | None = None
        try:
            request = await reader.readuntil(b"\r\n\r\n")
            target = request.split(b" ", 2)[1].decode()
            host, raw_port = target.rsplit(":", 1)
            _ = host
            upstream_reader, upstream_writer = await asyncio.open_connection("127.0.0.1", int(raw_port))
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            async def pipe(source: asyncio.StreamReader, destination: asyncio.StreamWriter) -> None:
                try:
                    while data := await source.read(65536):
                        destination.write(data)
                        await destination.drain()
                except (ConnectionError, asyncio.IncompleteReadError):
                    pass
            await asyncio.gather(pipe(reader, upstream_writer), pipe(upstream_reader, writer))
        finally:
            if upstream_writer is not None:
                upstream_writer.close()
                await upstream_writer.wait_closed()
            writer.close()
            await writer.wait_closed()

    proxy_server = await asyncio.start_server(tunnel_proxy, "127.0.0.1", 0)
    proxy_port = proxy_server.sockets[0].getsockname()[1]
    gateway = Gateway(
        host="127.0.0.1", port=0, generation_port=proxy_port,
        generation_credentials={"node-a": "x"}, max_active_connections=1,
        proxy_password="x",
    )
    await gateway.start()
    client_reader, client_writer = await asyncio.open_connection("127.0.0.1", gateway.port)
    token = base64.b64encode(b"hopline:x").decode()
    client_writer.write(f"CONNECT 127.0.0.1:{origin_port} HTTP/1.1\r\nProxy-Authorization: Basic {token}\r\n\r\n".encode())
    await client_writer.drain()
    response = await asyncio.wait_for(client_reader.readuntil(b"\r\n\r\n"), 3)
    if not response.startswith(b"HTTP/1.1 200"):
        raise RuntimeError(f"CONNECT failed: {response!r}")
    client_writer.write(b"pong")
    await client_writer.drain()
    echoed = await asyncio.wait_for(client_reader.readexactly(4), 3)
    if echoed != b"pong":
        raise RuntimeError(f"origin echo failed: {echoed!r}")
    client_writer.close()
    await client_writer.wait_closed()
    await gateway.stop()
    await gateway.wait_closed()
    proxy_server.close()
    await proxy_server.wait_closed()
    origin_server.close()
    await origin_server.wait_closed()
    print(f"https_proxy_acceptance=passed gateway_port={gateway.port} origin_port={origin_port}")


if __name__ == "__main__":
    asyncio.run(run())
