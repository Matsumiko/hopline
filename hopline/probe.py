from __future__ import annotations

import asyncio
import inspect
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
    def hostname(self) -> str:
        hostname = urlsplit(self.url).hostname
        if not hostname:
            raise ValueError("probe target must contain a hostname")
        return hostname


TargetProbe = Callable[[Node, ProbeTarget], bool | Awaitable[bool]]


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
        probe: TargetProbe = tcp_target_probe,
    ) -> None:
        if interval <= 0 or timeout <= 0 or timeout > interval:
            raise ValueError("probe interval and timeout are invalid")
        self.checker = checker
        self.nodes = nodes
        self.targets = tuple(ProbeTarget(target) for target in targets)
        if not self.targets:
            raise ValueError("at least one probe target is required")
        self.interval = interval
        self.timeout = timeout
        self.probe = probe
        self._stop = asyncio.Event()

    async def probe_once(self) -> list[HealthRecord]:
        records: list[HealthRecord] = []
        for index, node in enumerate(tuple(self.nodes())):
            target = self.targets[index % len(self.targets)]
            started = time.monotonic()
            try:
                result = self.probe(node, target)
                ok = await asyncio.wait_for(result, self.timeout) if inspect.isawaitable(result) else bool(result)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                records.append(self.checker.record_failure(node.id, type(error).__name__))
                continue
            latency_ms = (time.monotonic() - started) * 1000
            records.append(
                self.checker.record_success(node.id, latency_ms)
                if ok
                else self.checker.record_failure(node.id, "probe returned false")
            )
        return records

    async def run(self) -> None:
        while not self._stop.is_set():
            await self.probe_once()
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        self._stop.set()
