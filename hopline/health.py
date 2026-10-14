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
    cooldown_until: float = 0.0
    probe_after: float = 0.0
    consecutive_failures: int = 0
    consecutive_successes: int = 0


Probe = Callable[[Node], bool | Awaitable[bool]]


class HealthChecker:
    FAILURE_COOLDOWN = 30.0
    DEAD_BACKOFFS = (60.0, 120.0, 300.0, 900.0, 3600.0)

    def __init__(self, registry: SQLiteRegistry, *, probe: Probe | None = None, clock: Callable[[], float] = time.time) -> None:
        self.registry = registry
        self.probe = probe
        self.clock = clock

    def record_success(self, node_id: str, latency_ms: float | None = None) -> HealthRecord:
        previous = self.registry.health_record(node_id)
        successes = (previous.successes if previous else 0) + 1
        failures = previous.failures if previous else 0
        consecutive_successes = (previous.consecutive_successes if previous else 0) + 1
        consecutive_failures = 0
        if previous is None or previous.state == HealthState.HEALTHY:
            state = HealthState.HEALTHY
        elif consecutive_successes >= 3:
            state = HealthState.HEALTHY
        else:
            state = HealthState.DEGRADED
        return self.registry.save_health(
            node_id, state, successes, failures, latency_ms, None,
            cooldown_until=0.0, probe_after=0.0,
            consecutive_failures=consecutive_failures,
            consecutive_successes=consecutive_successes,
        )

    def record_failure(self, node_id: str, error: str) -> HealthRecord:
        previous = self.registry.health_record(node_id)
        successes = previous.successes if previous else 0
        failures = (previous.failures if previous else 0) + 1
        consecutive_failures = (previous.consecutive_failures if previous else 0) + 1
        now = self.clock()
        state = HealthState.DEAD if consecutive_failures >= 3 else HealthState.DEGRADED
        probe_after = 0.0
        if state == HealthState.DEAD:
            index = min(consecutive_failures - 3, len(self.DEAD_BACKOFFS) - 1)
            probe_after = now + self.DEAD_BACKOFFS[index]
        return self.registry.save_health(
            node_id, state, successes, failures,
            previous.latency_ms if previous else None, error[:200],
            cooldown_until=now + self.FAILURE_COOLDOWN,
            probe_after=probe_after,
            consecutive_failures=consecutive_failures,
            consecutive_successes=0,
        )

    def quarantine(self, node_id: str) -> HealthRecord:
        previous = self.registry.health_record(node_id)
        return self.registry.save_health(
            node_id, HealthState.QUARANTINE, previous.successes if previous else 0,
            previous.failures if previous else 0, previous.latency_ms if previous else None,
            previous.last_error if previous else None,
            cooldown_until=0.0,
            probe_after=self.clock() + self.DEAD_BACKOFFS[0],
            consecutive_failures=previous.consecutive_failures if previous else 0,
            consecutive_successes=0,
        )

    def is_available(self, node_id: str) -> bool:
        record = self.registry.health_record(node_id)
        if record is None or record.state in {HealthState.DEAD, HealthState.QUARANTINE}:
            return False if record is not None else True
        return self.clock() >= record.cooldown_until

    def should_probe(self, node_id: str) -> bool:
        record = self.registry.health_record(node_id)
        if record is None:
            return True
        if record.state in {HealthState.DEAD, HealthState.QUARANTINE}:
            return self.clock() >= record.probe_after
        return True


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
