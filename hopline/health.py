from __future__ import annotations

import asyncio
import inspect
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Awaitable, Callable

from .failures import PROBE_FAILED, FailureReason, classify_exception, parse_legacy
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
    conn_successes: int = 0
    conn_failures: int = 0
    latency_ewma_ms: float | None = None
    failure_category: str | None = None


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
            conn_successes=previous.conn_successes if previous else 0,
            conn_failures=previous.conn_failures if previous else 0,
            latency_ewma_ms=previous.latency_ewma_ms if previous else None,
            failure_category=None if previous is None else previous.failure_category,
        )

    def record_failure(self, node_id: str, reason: FailureReason | str) -> HealthRecord:
        failure = reason if isinstance(reason, FailureReason) else parse_legacy(reason) or FailureReason("unknown", str(reason))
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
            previous.latency_ms if previous else None, failure.code,
            cooldown_until=now + self.FAILURE_COOLDOWN,
            probe_after=probe_after,
            consecutive_failures=consecutive_failures,
            consecutive_successes=0,
            conn_successes=previous.conn_successes if previous else 0,
            conn_failures=previous.conn_failures if previous else 0,
            latency_ewma_ms=previous.latency_ewma_ms if previous else None,
            failure_category=failure.category,
        )

    def record_connection(self, node_id: str, *, ok: bool, latency_ms: float | None = None, reason: FailureReason | None = None) -> HealthRecord | None:
        """Track relay performance separately from active-probe liveness.

        Connection counters never change the health state; only the probe path does.
        This keeps "can the node be reached" distinct from "how well does it relay".
        """
        previous = self.registry.health_record(node_id)
        if previous is None:
            return None
        if ok:
            latency = latency_ms if latency_ms is not None else previous.latency_ms
            ewma = latency if previous.latency_ewma_ms is None else previous.latency_ewma_ms * 0.8 + latency * 0.2
            return self.registry.save_health(
                node_id, previous.state, previous.successes, previous.failures,
                previous.latency_ms, previous.last_error,
                cooldown_until=previous.cooldown_until, probe_after=previous.probe_after,
                consecutive_failures=previous.consecutive_failures,
                consecutive_successes=previous.consecutive_successes,
                conn_successes=previous.conn_successes + 1,
                conn_failures=previous.conn_failures,
                latency_ewma_ms=round(ewma, 1) if ewma is not None else None,
                failure_category=previous.failure_category,
            )
        failure = reason or FailureReason(PROBE_FAILED)
        return self.registry.save_health(
            node_id, previous.state, previous.successes, previous.failures,
            previous.latency_ms, previous.last_error,
            cooldown_until=previous.cooldown_until, probe_after=previous.probe_after,
            consecutive_failures=previous.consecutive_failures,
            consecutive_successes=previous.consecutive_successes,
            conn_successes=previous.conn_successes,
            conn_failures=previous.conn_failures + 1,
            latency_ewma_ms=previous.latency_ewma_ms,
            failure_category=failure.category,
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
            conn_successes=previous.conn_successes if previous else 0,
            conn_failures=previous.conn_failures if previous else 0,
            latency_ewma_ms=previous.latency_ewma_ms if previous else None,
            failure_category=previous.failure_category if previous else None,
        )

    def enable(self, node_id: str) -> HealthRecord | None:
        """Remove a manual quarantine so the node rejoins the candidate pool."""
        return self.registry.save_health(
            node_id, HealthState.DEGRADED, 0, 0, None, None,
            cooldown_until=0.0, probe_after=0.0,
            consecutive_failures=0, consecutive_successes=0,
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
            return self.record_failure(node.id, classify_exception(exc))
        latency_ms = (time.monotonic() - started) * 1000
        return self.record_success(node.id, latency_ms) if ok else self.record_failure(node.id, FailureReason(PROBE_FAILED))
