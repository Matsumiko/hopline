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

        # Connection performance is aggregated per protocol, separated from probe health.
        by_protocol = {protocol: {"ok": 0, "fail": 0, "latency": [], "probe_ok": 0, "probe_fail": 0} for protocol in protocols}
        protocol_of = {node.id: node.protocol for node in nodes}
        categories: dict[str, int] = {}
        for record in records:
            bucket = by_protocol.get(protocol_of.get(record.node_id, ""))
            if bucket is None:
                continue
            bucket["ok"] += record.conn_successes
            bucket["fail"] += record.conn_failures
            bucket["probe_ok"] += record.successes
            bucket["probe_fail"] += record.failures
            if record.latency_ewma_ms is not None:
                bucket["latency"].append(record.latency_ewma_ms)
            if record.failure_category:
                categories[record.failure_category.split(":", 1)[0]] = categories.get(record.failure_category.split(":", 1)[0], 0) + 1

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
            "# HELP hopline_protocol_connection_total Relay connections by protocol and outcome.",
            "# TYPE hopline_protocol_connection_total counter",
        ])
        for protocol, bucket in sorted(by_protocol.items()):
            lines.append(f'hopline_protocol_connection_total{{protocol="{protocol}",outcome="success"}} {bucket["ok"]}')
            lines.append(f'hopline_protocol_connection_total{{protocol="{protocol}",outcome="failure"}} {bucket["fail"]}')
        lines.extend([
            "# HELP hopline_protocol_probe_total Active probe results by protocol and outcome.",
            "# TYPE hopline_protocol_probe_total counter",
        ])
        for protocol, bucket in sorted(by_protocol.items()):
            lines.append(f'hopline_protocol_probe_total{{protocol="{protocol}",outcome="success"}} {bucket["probe_ok"]}')
            lines.append(f'hopline_protocol_probe_total{{protocol="{protocol}",outcome="failure"}} {bucket["probe_fail"]}')
        lines.extend([
            "# HELP hopline_protocol_latency_ewma_ms Mean EWMA latency by protocol.",
            "# TYPE hopline_protocol_latency_ewma_ms gauge",
        ])
        for protocol, bucket in sorted(by_protocol.items()):
            if bucket["latency"]:
                mean = sum(bucket["latency"]) / len(bucket["latency"])
                lines.append(f'hopline_protocol_latency_ewma_ms{{protocol="{protocol}"}} {round(mean, 1)}')
        lines.extend([
            "# HELP hopline_failure_nodes Nodes whose last failure has this category.",
            "# TYPE hopline_failure_nodes gauge",
        ])
        lines.extend(f'hopline_failure_nodes{{category="{category}"}} {count}' for category, count in sorted(categories.items()))
        lines.extend(self._resource_lines())
        lines.extend([
            "# HELP hopline_active_probe_enabled Whether active probing is configured.",
            "# TYPE hopline_active_probe_enabled gauge",
            f"hopline_active_probe_enabled {1 if self.probe_enabled else 0}",
        ])
        return ("\n".join(lines) + "\n").encode()

    def _resource_lines(self) -> list[str]:
        """Process resource gauges; bounded and credential-free."""
        try:
            import resource
            usage = resource.getrusage(resource.RUSAGE_SELF)
            max_rss = float(usage.ru_maxrss)
            import sys
            if sys.platform != "darwin":
                max_rss *= 1024.0  # ru_maxrss is KiB on Linux.
            cpu = float(usage.ru_utime + usage.ru_stime)
        except (ImportError, OSError, ValueError):
            return []
        return [
            "# HELP hopline_process_cpu_seconds_total CPU time consumed by the daemon.",
            "# TYPE hopline_process_cpu_seconds_total counter",
            f"hopline_process_cpu_seconds_total {round(cpu, 3)}",
            "# HELP hopline_process_resident_memory_bytes Peak resident memory of the daemon.",
            "# TYPE hopline_process_resident_memory_bytes gauge",
            f"hopline_process_resident_memory_bytes {int(max_rss)}",
        ]

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
