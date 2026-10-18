from __future__ import annotations

import asyncio
from typing import Any

from .health import HealthState
from .registry import SQLiteRegistry


class MetricsServer:
    def __init__(
        self,
        registry: SQLiteRegistry,
        *,
        host: str = "127.0.0.1",
        port: int = 18773,
        probe_enabled: bool = False,
    ) -> None:
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("metrics server must bind to localhost")
        self.registry = registry
        self.host = host
        self.requested_port = port
        self.probe_enabled = probe_enabled
        self.server: asyncio.AbstractServer | None = None

    @property
    def port(self) -> int | None:
        sockets = self.server.sockets if self.server else None
        return sockets[0].getsockname()[1] if sockets else None

    async def start(self) -> None:
        if self.server is not None:
            raise RuntimeError("metrics server is already running")
        self.server = await asyncio.start_server(self._handle, self.host, self.requested_port)

    async def stop(self) -> None:
        if self.server is None:
            return
        self.server.close()
        await self.server.wait_closed()
        self.server = None

    def render(self) -> bytes:
        nodes = self.registry.list_nodes()
        records = self.registry.list_health()
        counts = {state.value: 0 for state in HealthState}
        for record in records:
            counts[record.state.value] += 1
        protocols: dict[str, int] = {}
        for node in nodes:
            protocols[node.protocol] = protocols.get(node.protocol, 0) + 1
        lines = [
            "# HELP hopline_nodes Number of nodes in the registry.",
            "# TYPE hopline_nodes gauge",
            f"hopline_nodes {len(nodes)}",
            "# HELP hopline_health_nodes Number of nodes by health state.",
            "# TYPE hopline_health_nodes gauge",
        ]
        lines.extend(f'hopline_health_nodes{{state="{state}"}} {counts[state]}' for state in counts)
        lines.extend([
            "# HELP hopline_protocol_nodes Number of nodes by protocol.",
            "# TYPE hopline_protocol_nodes gauge",
        ])
        lines.extend(
            f'hopline_protocol_nodes{{protocol="{protocol}"}} {count}'
            for protocol, count in sorted(protocols.items())
        )
        lines.extend([
            "# HELP hopline_active_probe_enabled Whether active probing is configured.",
            "# TYPE hopline_active_probe_enabled gauge",
            f"hopline_active_probe_enabled {1 if self.probe_enabled else 0}",
        ])
        return ("\n".join(lines) + "\n").encode()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
            line = request.split(b"\r\n", 1)[0].decode("ascii", "replace")
            method, path, _version = line.split(" ", 2)
            if method != "GET" or path != "/metrics":
                body = b"not found\n"
                status = b"404 Not Found"
                content_type = b"text/plain; charset=utf-8"
            else:
                body = self.render()
                status = b"200 OK"
                content_type = b"text/plain; version=0.0.4"
            writer.write(
                b"HTTP/1.1 " + status + b"\r\nContent-Type: " + content_type
                + b"\r\nContent-Length: " + str(len(body)).encode()
                + b"\r\nConnection: close\r\n\r\n" + body
            )
            await writer.drain()
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, ValueError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()
