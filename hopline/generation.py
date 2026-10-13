from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass(slots=True)
class Generation:
    label: str
    port: int
    active_connections: int = 0
    accepting: bool = True
    drained: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        self.drained.set()

    def acquire(self) -> None:
        if not self.accepting:
            raise RuntimeError(f"generation {self.label} is draining")
        self.active_connections += 1
        self.drained.clear()

    def release(self) -> None:
        if self.active_connections <= 0:
            raise RuntimeError(f"generation {self.label} lease underflow")
        self.active_connections -= 1
        if self.active_connections == 0:
            self.drained.set()


@dataclass(frozen=True, slots=True)
class GenerationLease:
    generation: Generation


class GenerationManager:
    def __init__(self) -> None:
        self.active: Generation | None = None
        self._draining: list[Generation] = []

    def publish(self, generation: Generation) -> None:
        if not generation.accepting:
            raise ValueError("cannot publish a draining generation")
        previous = self.active
        self.active = generation
        if previous is not None:
            previous.accepting = False
            self._draining.append(previous)

    def acquire(self) -> GenerationLease:
        if self.active is None:
            raise RuntimeError("no active generation")
        self.active.acquire()
        return GenerationLease(self.active)

    async def release(self, lease: GenerationLease) -> None:
        lease.generation.release()
        if lease.generation.active_connections == 0 and lease.generation in self._draining:
            self._draining.remove(lease.generation)

    async def wait_drained(self, generation: Generation) -> None:
        await generation.drained.wait()
