from __future__ import annotations

import asyncio
import base64
import binascii
import hmac
import re
import time
from collections.abc import Callable

from .health import HealthState
from .picker import NodePicker
from .sticky import StickySessionStore

class Gateway:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        generation_port: int,
        generation_credentials: dict[str, str],
        health_state: Callable[[str], HealthState | str | None] | None = None,
        health_available: Callable[[str], bool] | None = None,
        country_metadata: Callable[[str], tuple[str, float] | None] | None = None,
        country_max_age: float = 60 * 60,
        clock: Callable[[], float] | None = None,
        record_success: Callable[[str], None] | None = None,
        record_failure: Callable[[str, str], None] | None = None,
        max_active_connections: int = 64,
        proxy_username: str = "hopline",
        proxy_password: str = "",
        sticky_ttl: float = 10 * 60,
        sticky_store: StickySessionStore | None = None,
    ) -> None:
        if max_active_connections <= 0:
            raise ValueError("max_active_connections must be positive")
        if country_max_age <= 0:
            raise ValueError("country_max_age must be positive")
        if not proxy_username or not proxy_password:
            raise ValueError("proxy authentication credentials must be non-empty")
        self.host = host
        self._requested_port = port
        self._generation_port = generation_port
        self._generation_credentials = dict(generation_credentials)
        self._picker = NodePicker(
            generation_credentials,
            state=health_state,
            available=health_available,
        )
        self._country_metadata = country_metadata or (lambda _node_id: None)
        self._country_max_age = country_max_age
        self._clock = clock or time.time
        self._record_success = record_success
        self._record_failure = record_failure
        self._max_active_connections = max_active_connections
        self._proxy_username = proxy_username
        self._active_connections: dict[str, int] = {node_id: 0 for node_id in generation_credentials}
        self._proxy_password = proxy_password
        self._sticky = sticky_store or StickySessionStore(ttl=sticky_ttl)
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
        self._server = await asyncio.start_server(self._accept, self.host, self._requested_port)

    def publish_generation(self, generation_port: int, generation_credentials: dict[str, str]) -> None:
        """Publish one generation for new connections; existing relays are untouched."""
        if not generation_credentials:
            raise ValueError("generation must contain at least one node")
        self._generation_port = generation_port
        self._generation_credentials = dict(generation_credentials)
        self._picker.replace(generation_credentials)
        self._active_connections = {
            node_id: self._active_connections.get(node_id, 0)
            for node_id in generation_credentials
        }

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

    async def _accept(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        if not self._accepting:
            writer.close()
            await writer.wait_closed()
            return
        task = asyncio.create_task(self._handle(reader, writer))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _handle(self, reader: asyncio.StreamReader, client: asyncio.StreamWriter) -> None:
        upstream: asyncio.StreamWriter | None = None
        try:
            method, target, headers = await asyncio.wait_for(self._read_headers(reader), 5)
            if method.upper() != "CONNECT":
                await self._respond(client, b"HTTP/1.1 501 Not Implemented\r\n\r\n")
                return
            auth_value = headers.get("proxy-authorization")
            if auth_value is None:
                await self._respond(client, b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")
                return
            route = self._route_from_auth(auth_value)
            if route is None:
                await self._respond(client, b"HTTP/1.1 407 Proxy Authentication Required\r\n\r\n")
                return
            requested_node, sticky_session, country = self._candidates_for_route(route)
            country_filter = self._country_filter(country)
            candidates = self._picker.candidates(requested_node, eligible=country_filter)
            if sticky_session is not None and requested_node != "rotate":
                candidates += [
                    node_id for node_id in self._picker.candidates("rotate", eligible=country_filter)
                    if node_id not in candidates
                ]
            if not candidates:
                await self._respond(client, b"HTTP/1.1 503 Service Unavailable\r\n\r\n")
                return

            attempted_any = False
            last_response: bytes | None = None
            for node_id in candidates:
                if not self._reserve(node_id):
                    continue
                attempted_any = True
                try:
                    upstream_reader, upstream = await asyncio.wait_for(
                        asyncio.open_connection("127.0.0.1", self._generation_port), 3
                    )
                    credential = self._generation_credentials[node_id]
                    token = base64.b64encode(f"{node_id}:{credential}".encode()).decode()
                    upstream.write(
                        f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n".encode()
                        + f"Proxy-Authorization: Basic {token}\r\n\r\n".encode()
                    )
                    await upstream.drain()
                    response = await asyncio.wait_for(self._read_response(upstream_reader), 3)
                    if response.startswith(b"HTTP/1.1 200"):
                        if sticky_session is not None:
                            self._sticky.bind(sticky_session, node_id)
                        if self._record_success is not None:
                            self._record_success(node_id)
                        await self._respond(client, b"HTTP/1.1 200 Connection Established\r\n\r\n")
                        await self._relay(reader, client, upstream_reader, upstream)
                        return
                    last_response = response
                    self._report_failure(node_id, "upstream_rejected")
                except (asyncio.TimeoutError, asyncio.IncompleteReadError, ConnectionError, OSError) as error:
                    self._report_failure(node_id, type(error).__name__)
                finally:
                    self._release(node_id)
                    if upstream is not None and not upstream.is_closing():
                        upstream.close()
                        try:
                            await upstream.wait_closed()
                        except ConnectionError:
                            pass
                    upstream = None

            if not attempted_any:
                await self._respond(client, b"HTTP/1.1 503 Service Unavailable\r\n\r\n")
            else:
                await self._respond(client, last_response or b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
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

    def _reserve(self, node_id: str) -> bool:
        active = self._active_connections.get(node_id, 0)
        if active >= self._max_active_connections:
            return False
        self._active_connections[node_id] = active + 1
        return True

    def _release(self, node_id: str) -> None:
        active = self._active_connections.get(node_id, 0)
        if active <= 0:
            raise RuntimeError(f"active connection underflow for {node_id}")
        self._active_connections[node_id] = active - 1

    def _report_failure(self, node_id: str, error: str) -> None:
        if self._record_failure is not None:
            self._record_failure(node_id, error)

    async def _relay(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        upstream_reader: asyncio.StreamReader,
        upstream_writer: asyncio.StreamWriter,
    ) -> None:
        async def pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            try:
                while data := await reader.read(65536):
                    writer.write(data)
                    await writer.drain()
            except (ConnectionError, asyncio.IncompleteReadError, OSError):
                pass
            finally:
                try:
                    writer.write_eof()
                except (AttributeError, OSError, RuntimeError):
                    pass

        tasks = [
            asyncio.create_task(pipe(client_reader, upstream_writer)),
            asyncio.create_task(pipe(upstream_reader, client_writer)),
        ]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    @staticmethod
    async def _read_headers(reader: asyncio.StreamReader) -> tuple[str, str, dict[str, str]]:
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

    def _route_from_auth(self, value: str | None) -> tuple[str, str | None, str | None] | None:
        if value is None or not value.lower().startswith("basic "):
            return None
        try:
            decoded = base64.b64decode(value[6:], validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return None
        username, separator, password = decoded.partition(":")
        if not separator or not username or not hmac.compare_digest(password, self._proxy_password):
            return None
        if username == self._proxy_username or username == "rotate":
            return "rotate", None, None
        if username.startswith("sticky-") and username[7:]:
            return "rotate", username[7:], None
        if username in self._generation_credentials:
            return username, None, None
        if username.startswith("node-") and username[5:] in self._generation_credentials:
            return username[5:], None, None
        if username.startswith("country-"):
            value = username[8:]
            country, separator, session = value.partition("-sticky-")
            if re.fullmatch(r"[A-Za-z]{2}", country) and (not separator or bool(session)):
                return "rotate", session or None, country.upper()
        return None

    def _candidates_for_route(
        self, route: tuple[str, str | None, str | None]
    ) -> tuple[str, str | None, str | None]:
        requested_node, sticky_session, country = route
        if sticky_session is None:
            return requested_node, None, country
        bound = self._sticky.lookup(
            sticky_session,
            eligible=lambda node_id: bool(
                self._picker.candidates(node_id, eligible=self._country_filter(country))
            ),
        )
        return (bound or "rotate"), sticky_session, country

    def _country_filter(self, country: str | None) -> Callable[[str], bool] | None:
        if country is None:
            return None

        def eligible(node_id: str) -> bool:
            metadata = self._country_metadata(node_id)
            if metadata is None:
                return False
            code, checked_at = metadata
            return code.upper() == country and 0 <= self._clock() - checked_at <= self._country_max_age

        return eligible

    @staticmethod
    def _target_host_port(target: str) -> tuple[str, int]:
        host, separator, raw_port = target.rpartition(":")
        if not separator or not host:
            raise ValueError("CONNECT target must include a port")
        port = int(raw_port)
        if not 1 <= port <= 65535:
            raise ValueError("CONNECT target port is out of range")
        return host, port
