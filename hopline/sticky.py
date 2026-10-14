from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class StickyBinding:
    node_id: str
    expires_at: float


class StickySessionStore:
    """Process-local session-to-node bindings with idle TTL renewal."""

    def __init__(self, *, ttl: float = 10 * 60, clock: Callable[[], float] = time.monotonic) -> None:
        if ttl <= 0:
            raise ValueError("sticky TTL must be positive")
        self.ttl = ttl
        self._clock = clock
        self._bindings: dict[str, StickyBinding] = {}

    def lookup(self, session_id: str, *, eligible: Callable[[str], bool]) -> str | None:
        binding = self._bindings.get(session_id)
        if binding is None:
            return None
        if binding.expires_at <= self._clock() or not eligible(binding.node_id):
            self._bindings.pop(session_id, None)
            return None
        return binding.node_id

    def bind(self, session_id: str, node_id: str) -> None:
        self._bindings[session_id] = StickyBinding(node_id, self._clock() + self.ttl)

    def forget(self, session_id: str) -> None:
        self._bindings.pop(session_id, None)
