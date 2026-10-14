from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Awaitable, Callable

from .models import Node
from .registry import SQLiteRegistry


class HealthState(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DEAD = "dead"
    QUARANTINE = "quarantine"


@dataclass(frozen=True, slots=True)
class HealthRecord:
    node_id: str
    state: HealthState
    successes: int
    failures: int
    latency_ms: float | None
    last_error: str | None
    updated_at: float


Probe = Callable[[Node], bool | Awaitable[bool]]


class HealthChecker:
    def __init__(self, registry: SQLiteRegistry, *, probe: Probe | None = None) -> None:
        self.registry = registry
        self.probe = probe

    def record_success(self, node_id: str, latency_ms: float | None = None) -> HealthRecord:
        previous = self.registry.health_record(node_id)
        successes = (previous.successes if previous else 0) + 1
        failures = previous.failures if previous else 0
        state = HealthState.HEALTHY if failures == 0 or successes >= failures else HealthState.DEGRADED
        return self.registry.save_health(node_id, state, successes, failures, latency_ms, None)

    def record_failure(self, node_id: str, error: str) -> HealthRecord:
        previous = self.registry.health_record(node_id)
        successes = previous.successes if previous else 0
        failures = (previous.failures if previous else 0) + 1
        state = HealthState.DEAD if failures >= 3 else HealthState.DEGRADED
        return self.registry.save_health(node_id, state, successes, failures, previous.latency_ms if previous else None, error[:200])

    def quarantine(self, node_id: str) -> HealthRecord:
        previous = self.registry.health_record(node_id)
        return self.registry.save_health(
            node_id, HealthState.QUARANTINE, previous.successes if previous else 0,
            previous.failures if previous else 0, previous.latency_ms if previous else None,
            previous.last_error if previous else None,
        )

    async def probe_node(self, node: Node) -> HealthRecord:
        if self.probe is None:
            raise RuntimeError("active probe is not configured")
        started = time.monotonic()
        try:
            result = self.probe(node)
            ok = await result if inspect.isawaitable(result) else result
        except Exception as exc:
            return self.record_failure(node.id, type(exc).__name__)
        latency_ms = (time.monotonic() - started) * 1000
        return self.record_success(node.id, latency_ms) if ok else self.record_failure(node.id, "probe returned false")
