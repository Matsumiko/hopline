from __future__ import annotations

import asyncio
import base64

from hopline.gateway import Gateway


async def run(concurrency: int = 16, limit: int = 4) -> None:
    admitted = 0
    release = asyncio.Event()

    async def upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal admitted
        try:
            await reader.readuntil(b"\r\n\r\n")
            admitted += 1
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            await release.wait()
        finally:
            writer.close()
            await writer.wait_closed()

    upstream_server = await asyncio.start_server(upstream, "127.0.0.1", 0)
    upstream_port = upstream_server.sockets[0].getsockname()[1]
    gateway = Gateway(
        host="127.0.0.1", port=0, generation_port=upstream_port,
        generation_credentials={"node-a": "x"}, max_active_connections=limit,
        proxy_password="x",
    )
    await gateway.start()
    token = base64.b64encode(b"hopline:x").decode()

    async def request() -> int:
        reader, writer = await asyncio.open_connection("127.0.0.1", gateway.port)
        writer.write(f"CONNECT origin.test:443 HTTP/1.1\r\nProxy-Authorization: Basic {token}\r\n\r\n".encode())
        await writer.drain()
        response = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3)
        status = int(response.split(b" ", 2)[1])
        if status == 200:
            await asyncio.sleep(0.01)
        writer.close()
        await writer.wait_closed()
        return status

    statuses = await asyncio.gather(*(request() for _ in range(concurrency)))
    release.set()
    await gateway.stop()
    await gateway.wait_closed()
    upstream_server.close()
    await upstream_server.wait_closed()
    successes = statuses.count(200)
    rejected = statuses.count(503)
    if successes != limit or rejected != concurrency - limit or admitted != limit:
        raise RuntimeError(f"load invariant failed: successes={successes} rejected={rejected} admitted={admitted}")
    print(f"gateway_load=passed concurrency={concurrency} limit={limit} admitted={admitted} rejected={rejected}")


if __name__ == "__main__":
    asyncio.run(run())
