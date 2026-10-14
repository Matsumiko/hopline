from __future__ import annotations

import asyncio
import json
from typing import Any

from .health import HealthState


class ControlServer:
    def __init__(self, registry: SQLiteRegistry, *, host: str = "127.0.0.1", port: int = 18772) -> None:
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("control API must bind to localhost")
        self.registry = registry
        self.host = host
        self.requested_port = port
        self.server: asyncio.AbstractServer | None = None

    @property
    def port(self) -> int | None:
        sockets = self.server.sockets if self.server else None
        return sockets[0].getsockname()[1] if sockets else None

    async def start(self) -> None:
        if self.server is not None:
            raise RuntimeError("control API is already running")
        self.server = await asyncio.start_server(self._handle, self.host, self.requested_port)

    async def stop(self) -> None:
        if self.server is None:
            return
        self.server.close()
        await self.server.wait_closed()
        self.server = None

    def status(self) -> dict[str, Any]:
        nodes = self.registry.list_nodes()
        health = self.registry.list_health()
        states = {state.value: 0 for state in HealthState}
        states["unknown"] = max(0, len(nodes) - len(health))
        for record in health:
            states[record.state.value] += 1
        return {"nodes": len(nodes), "health": states, "schema_version": self.registry.schema_version()}

    def nodes(self) -> list[dict[str, Any]]:
        records = {record.node_id: record for record in self.registry.list_health()}
        result = []
        for node in self.registry.list_nodes():
            record = records.get(node.id)
            result.append(
                {
                    "id": node.id,
                    "protocol": node.protocol,
                    "server": node.server,
                    "port": node.port,
                    "name": node.name,
                    "health": record.state.value if record else "unknown",
                    "successes": record.successes if record else 0,
                    "failures": record.failures if record else 0,
                    "latency_ms": record.latency_ms if record else None,
                }
            )
        return result

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
            line = request.split(b"\r\n", 1)[0].decode("ascii", "replace")
            method, path, _version = line.split(" ", 2)
            if method != "GET":
                await self._respond(writer, 405, {"error": "method_not_allowed"})
            elif path == "/status":
                await self._respond(writer, 200, self.status())
            elif path == "/nodes":
                await self._respond(writer, 200, {"nodes": self.nodes()})
            else:
                await self._respond(writer, 404, {"error": "not_found"})
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, ValueError):
            await self._respond(writer, 400, {"error": "bad_request"})
        finally:
            writer.close()
            await writer.wait_closed()

    @staticmethod
    async def _respond(writer: asyncio.StreamWriter, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        reason = {200: "OK", 400: "Bad Request", 404: "Not Found", 405: "Method Not Allowed"}[status]
        writer.write(
            f"HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body
        )
        await writer.drain()
