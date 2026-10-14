from __future__ import annotations

from collections.abc import Callable, Iterable

from .health import HealthState


class NodePicker:
    """Select eligible node IDs while preserving rotate order."""

    def __init__(
        self,
        node_ids: Iterable[str],
        *,
        state: Callable[[str], HealthState | str | None] | None = None,
        available: Callable[[str], bool] | None = None,
    ) -> None:
        self._node_ids = tuple(node_ids)
        self._state = state or (lambda _node_id: None)
        self._available = available or (lambda _node_id: True)
        self._next = 0

    def replace(self, node_ids: Iterable[str]) -> None:
        self._node_ids = tuple(node_ids)
        self._next = 0

    def candidates(self, requested: str | None, *, eligible: Callable[[str], bool] | None = None) -> list[str]:
        if requested and requested != "rotate":
            return [requested] if requested in self._node_ids and self._eligible(requested, eligible) else []
        if not self._node_ids:
            return []
        ordered = [
            self._node_ids[(self._next + offset) % len(self._node_ids)]
            for offset in range(len(self._node_ids))
        ]
        self._next = (self._next + 1) % len(self._node_ids)
        return [node_id for node_id in ordered if self._eligible(node_id, eligible)]

    def _eligible(self, node_id: str, eligible: Callable[[str], bool] | None = None) -> bool:
        state = self._state(node_id)
        return self._available(node_id) and (eligible is None or eligible(node_id)) and state not in {
            HealthState.DEAD, HealthState.QUARANTINE, "dead", "quarantine"
        }
