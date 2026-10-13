from __future__ import annotations

import asyncio
import base64
import binascii

class Gateway:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        generation_port: int,
        generation_credentials: dict[str, str],
    ) -> None:
        self.host = host
        self._requested_port = port
        self._generation_port = generation_port
        self._generation_credentials = dict(generation_credentials)
        self._node_order = tuple(generation_credentials)
        self._next_node = 0
        self._accepting = False
        self._server: asyncio.AbstractServer | None = None
        self._tasks: set[asyncio.Task[None]] = set()
    @property
    def port(self) -> int | None:
        if self._server is None or not self._server.sockets:
            return None
        return int(self._server.sockets[0].getsockname()[1])

    async def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("gateway is already running")
        self._accepting = True
        self._server = await asyncio.start_server(
            self._accept, self.host, self._requested_port
        )

    def publish_generation(
        self, generation_port: int, generation_credentials: dict[str, str]
    ) -> None:
        """Publish one generation for new connections; existing relays are untouched."""
        if not generation_credentials:
            raise ValueError("generation must contain at least one node")
        self._generation_port = generation_port
        self._generation_credentials = dict(generation_credentials)
        self._node_order = tuple(generation_credentials)
        self._next_node = 0

    async def stop(self) -> None:
        """Stop accepting new clients; preserve existing relay streams."""
        self._accepting = False

    async def wait_closed(self) -> None:
        """Drain relay handlers, then close the listener."""
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)
        server = self._server
        self._server = None
        if server is not None:
            server.close()
            await server.wait_closed()

    async def _accept(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        if not self._accepting:
            writer.close()
            await writer.wait_closed()
            return
        task = asyncio.create_task(self._handle(reader, writer))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _handle(
        self, reader: asyncio.StreamReader, client: asyncio.StreamWriter
    ) -> None:
        upstream: asyncio.StreamWriter | None = None
        try:
            request = await asyncio.wait_for(self._read_headers(reader), 5)
            method, target, headers = request
            if method.upper() != "CONNECT":
                await self._respond(client, b"HTTP/1.1 501 Not Implemented\r\n\r\n")
                return
            requested_node = self._node_from_auth(headers.get("proxy-authorization"))
            node_id = self._select_node(requested_node)
            if node_id is None:
                await self._respond(client, b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")
                return
            upstream = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", self._generation_port), 3
            )
            upstream_reader, upstream = upstream
            credential = self._generation_credentials[node_id]
            token = base64.b64encode(f"{node_id}:{credential}".encode()).decode()
            upstream.write(
                f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n".encode()
                + f"Proxy-Authorization: Basic {token}\r\n\r\n".encode()
            )
            await upstream.drain()
            response = await asyncio.wait_for(self._read_response(upstream_reader), 3)
            if not response.startswith(b"HTTP/1.1 200"):
                await self._respond(client, response)
                return
            await self._respond(client, b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await self._relay(reader, client, upstream_reader, upstream)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError, OSError, ValueError):
            if not client.is_closing():
                try:
                    await self._respond(client, b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                except ConnectionError:
                    pass
        finally:
            if upstream is not None and not upstream.is_closing():
                upstream.close()
                try:
                    await upstream.wait_closed()
                except ConnectionError:
                    pass
            if not client.is_closing():
                client.close()
                try:
                    await client.wait_closed()
                except ConnectionError:
                    pass

    async def _relay(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        upstream_reader: asyncio.StreamReader,
        upstream_writer: asyncio.StreamWriter,
    ) -> None:
        async def pipe(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            try:
                while data := await reader.read(65536):
                    writer.write(data)
                    await writer.drain()
            except (ConnectionError, asyncio.IncompleteReadError):
                pass
            finally:
                try:
                    writer.write_eof()
                except (AttributeError, OSError, RuntimeError):
                    pass

        await asyncio.gather(
            pipe(client_reader, upstream_writer),
            pipe(upstream_reader, client_writer),
        )

    @staticmethod
    async def _read_headers(
        reader: asyncio.StreamReader,
    ) -> tuple[str, str, dict[str, str]]:
        raw = await reader.readuntil(b"\r\n\r\n")
        lines = raw.decode("latin-1").split("\r\n")
        method, target, _version = lines[0].split(" ", 2)
        headers: dict[str, str] = {}
        for line in lines[1:]:
            if line and ":" in line:
                key, value = line.split(":", 1)
                headers[key.lower()] = value.strip()
        return method, target, headers

    @staticmethod
    async def _read_response(reader: asyncio.StreamReader) -> bytes:
        return await reader.readuntil(b"\r\n\r\n")

    @staticmethod
    async def _respond(writer: asyncio.StreamWriter, response: bytes) -> None:
        writer.write(response)
        await writer.drain()

    @staticmethod
    def _node_from_auth(value: str | None) -> str | None:
        if value is None or not value.lower().startswith("basic "):
            return None
        try:
            decoded = base64.b64decode(value[6:], validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return None
        username, separator, _password = decoded.partition(":")
        return username if separator and username else None

    def _select_node(self, requested: str | None) -> str | None:
        if requested == "rotate":
            if not self._node_order:
                return None
            node_id = self._node_order[self._next_node % len(self._node_order)]
            self._next_node += 1
            return node_id
        if requested in self._generation_credentials:
            return requested
        return None

    @staticmethod
    def _target_host_port(target: str) -> tuple[str, int]:
        host, separator, raw_port = target.rpartition(":")
        if not separator or not host:
            raise ValueError("CONNECT target must include a port")
        port = int(raw_port)
        if not 1 <= port <= 65535:
            raise ValueError("CONNECT target port is out of range")
        return host, port
