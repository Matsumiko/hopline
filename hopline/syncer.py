from __future__ import annotations

import base64
import binascii
import hashlib
from dataclasses import dataclass
from .engine import SingBoxEngine
from .generation import Generation
from .models import Node
from .parser import parse_vless
from .registry import SQLiteRegistry


@dataclass(frozen=True, slots=True)
class SyncResult:
    source: str
    changed: bool
    parsed_nodes: int
    invalid_entries: int
    used_last_valid: bool


class Syncer:
    def __init__(
        self,
        registry: SQLiteRegistry,
        *,
        max_body_bytes: int = 2 * 1024 * 1024,
        max_nodes: int = 2000,
    ) -> None:
        if max_body_bytes < 1 or max_nodes < 1:
            raise ValueError("sync limits must be positive")
        self.registry = registry
        self.max_body_bytes = max_body_bytes
        self.max_nodes = max_nodes

    def sync_text(self, source: str, body: bytes) -> SyncResult:
        if len(body) > self.max_body_bytes:
            raise ValueError("subscription body exceeds configured limit")
        entries = self._decode_entries(body)
        nodes: dict[str, Node] = {}
        invalid = 0
        for entry in entries:
            if len(nodes) >= self.max_nodes:
                break
            try:
                node = parse_vless(entry, source=source)
            except (ValueError, UnicodeError):
                invalid += 1
                continue
            nodes[node.id] = node

        if not nodes:
            return SyncResult(source, False, 0, invalid, True)
        snapshot_hash = hashlib.sha256(
            "\n".join(sorted(nodes)).encode("ascii")
        ).hexdigest()
        changed = self.registry.replace_subscription(source, snapshot_hash, nodes.values())
        return SyncResult(source, changed, len(nodes), invalid, False)

    async def sync_text_and_apply(
        self,
        source: str,
        body: bytes,
        engine: SingBoxEngine,
    ) -> tuple[SyncResult, Generation]:
        result = self.sync_text(source, body)
        nodes = self.registry.list_nodes()
        if not nodes:
            raise ValueError("subscription snapshot contains no usable nodes")
        generation = await engine.apply_nodes(nodes)
        return result, generation

    @staticmethod
    def _decode_entries(body: bytes) -> list[str]:
        text = body.decode("utf-8", errors="strict").strip()
        entries = [line.strip() for line in text.splitlines() if line.strip()]
        if any(line.lower().startswith("vless://") for line in entries):
            return entries
        try:
            decoded = base64.b64decode(text, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeError, ValueError):
            return entries
        return [line.strip() for line in decoded.splitlines() if line.strip()]
