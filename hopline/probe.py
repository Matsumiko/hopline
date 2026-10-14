from __future__ import annotations

import asyncio
import base64
import inspect
import ssl
import time
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass
from urllib.parse import urlsplit

from .health import HealthChecker, HealthRecord
from .models import Node


@dataclass(frozen=True, slots=True)
class ProbeTarget:
    url: str

    @property
    def parsed(self):
        parsed = urlsplit(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("probe target must be an HTTP(S) URL")
        return parsed

    @property
    def hostname(self) -> str:
        return self.parsed.hostname or ""

    @property
    def port(self) -> int:
        return self.parsed.port or (443 if self.parsed.scheme == "https" else 80)

    @property
    def path(self) -> str:
        parsed = self.parsed
        return parsed.path or "/"


TargetProbe = Callable[[Node, ProbeTarget], bool | Awaitable[bool]]


async def http_connect_probe(
    node: Node,
    target: ProbeTarget,
    *,
    proxy_host: str = "127.0.0.1",
    proxy_port: int = 18771,
) -> bool:
    """Probe a target through the sing-box mixed inbound using this node's auth user."""
    reader, writer = await asyncio.open_connection(proxy_host, proxy_port)
    try:
        token = base64.b64encode(f"{node.id}:{node.credential}".encode()).decode()
        writer.write(
            f"CONNECT {target.hostname}:{target.port} HTTP/1.1\r\n"
            f"Host: {target.hostname}:{target.port}\r\n"
            f"Proxy-Authorization: Basic {token}\r\n\r\n".encode()
        )
        await writer.drain()
        response = await reader.readuntil(b"\r\n\r\n")
        if not response.startswith(b"HTTP/1.1 200"):
            return False
        if target.parsed.scheme == "https":
            context = ssl.create_default_context()
            await writer.start_tls(context, server_hostname=target.hostname)
        writer.write(
            f"GET {target.path} HTTP/1.1\r\nHost: {target.hostname}\r\nConnection: close\r\n\r\n".encode()
        )
        await writer.drain()
        status_line = await reader.readline()
        parts = status_line.split(b" ", 2)
        return len(parts) >= 2 and parts[1].isdigit() and 200 <= int(parts[1]) < 400
    finally:
        writer.close()
        await writer.wait_closed()


async def tcp_target_probe(node: Node, target: ProbeTarget) -> bool:
    """Check node endpoint TCP reachability; target identifies the configured policy."""
    del target
    _reader, writer = await asyncio.wait_for(asyncio.open_connection(node.server, node.port), 5)
    writer.close()
    await writer.wait_closed()
    return True


class ActiveProbeScheduler:
    def __init__(
        self,
        checker: HealthChecker,
        nodes: Callable[[], Iterable[Node]],
        targets: Iterable[str],
        *,
        interval: float = 5 * 60,
        timeout: float = 5,
        concurrency: int = 10,
        probe: TargetProbe = tcp_target_probe,
    ) -> None:
        if interval <= 0 or timeout <= 0 or timeout > interval or concurrency <= 0:
            raise ValueError("probe interval, timeout, and concurrency are invalid")
        self.checker = checker
        self.nodes = nodes
        self.targets = tuple(ProbeTarget(target) for target in targets)
        if not self.targets:
            raise ValueError("at least one probe target is required")
        self.interval = interval
        self.timeout = timeout
        self.concurrency = concurrency
        self.probe = probe
        self._stop = asyncio.Event()

    async def _probe_one(self, index: int, node: Node) -> HealthRecord | None:
        if not self.checker.should_probe(node.id):
            return None
        target = self.targets[index % len(self.targets)]
        started = time.monotonic()
        try:
            result = self.probe(node, target)
            ok = await asyncio.wait_for(result, self.timeout) if inspect.isawaitable(result) else bool(result)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            return self.checker.record_failure(node.id, type(error).__name__)
        latency_ms = (time.monotonic() - started) * 1000
        return self.checker.record_success(node.id, latency_ms) if ok else self.checker.record_failure(node.id, "probe returned false")

    async def probe_once(self) -> list[HealthRecord]:
        nodes = tuple(self.nodes())
        semaphore = asyncio.Semaphore(self.concurrency)

        async def queued(index: int, node: Node) -> HealthRecord | None:
            async with semaphore:
                return await self._probe_one(index, node)

        results = await asyncio.gather(*(queued(index, node) for index, node in enumerate(nodes)))
        return [record for record in results if record is not None]

    async def run(self) -> None:
        while not self._stop.is_set():
            await self.probe_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        self._stop.set()
