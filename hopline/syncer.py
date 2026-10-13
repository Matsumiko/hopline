from __future__ import annotations

import base64
import binascii
import hashlib
import urllib.error
from dataclasses import dataclass

from .engine import SingBoxEngine
from .fetcher import SubscriptionFetcher
from .generation import Generation
from .models import Node
from .parser import parse_share_link
from .registry import SQLiteRegistry


@dataclass(frozen=True, slots=True)
class SyncResult:
    source: str
    changed: bool
    parsed_nodes: int
    invalid_entries: int
    used_last_valid: bool
    status: int = 200
    not_modified: bool = False


class Syncer:
    def __init__(
        self,
        registry: SQLiteRegistry,
        *,
        max_body_bytes: int = 2 * 1024 * 1024,
        max_nodes: int = 2000,
        fetcher: SubscriptionFetcher | None = None,
    ) -> None:
        if max_body_bytes < 1 or max_nodes < 1:
            raise ValueError("sync limits must be positive")
        self.registry = registry
        self.max_body_bytes = max_body_bytes
        self.max_nodes = max_nodes
        self.fetcher = fetcher or SubscriptionFetcher(max_body_bytes=max_body_bytes)

    def sync_text(
        self,
        source: str,
        body: bytes,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> SyncResult:
        if len(body) > self.max_body_bytes:
            raise ValueError("subscription body exceeds configured limit")
        entries = self._decode_entries(body)
        nodes: dict[str, Node] = {}
        invalid = 0
        for entry in entries:
            if len(nodes) >= self.max_nodes:
                break
            try:
                node = parse_share_link(entry, source=source)
            except (ValueError, UnicodeError):
                invalid += 1
                continue
            nodes[node.id] = node
        if not nodes:
            return SyncResult(source, False, 0, invalid, True)
        snapshot_hash = hashlib.sha256("\n".join(sorted(nodes)).encode("ascii")).hexdigest()
        changed = self.registry.replace_subscription(
            source, snapshot_hash, nodes.values(), body=body,
            etag=etag, last_modified=last_modified,
        )
        return SyncResult(source, changed, len(nodes), invalid, False)

    async def sync_url(self, url: str) -> SyncResult:
        metadata = self.registry.subscription_metadata(url)
        try:
            fetched = await self.fetcher.fetch(
                url,
                etag=metadata["etag"] if metadata else None,
                last_modified=metadata["last_modified"] if metadata else None,
            )
        except (OSError, urllib.error.URLError, TimeoutError):
            if not metadata or metadata["body"] is None:
                raise
            return SyncResult(url, False, len(self.registry.list_nodes()), 0, True, status=0)
        if fetched.not_modified:
            return SyncResult(
                url, False, len(self.registry.list_nodes()), 0, False,
                status=304, not_modified=True,
            )
        if fetched.body is None:
            raise ValueError("subscription fetch returned no body")
        synced = self.sync_text(
            url, fetched.body, etag=fetched.etag,
            last_modified=fetched.last_modified,
        )
        return SyncResult(
            synced.source, synced.changed, synced.parsed_nodes,
            synced.invalid_entries, synced.used_last_valid, status=fetched.status,
        )

    async def sync_url_and_apply(self, url: str, engine: SingBoxEngine) -> tuple[SyncResult, Generation]:
        result = await self.sync_url(url)
        nodes = self.registry.list_nodes()
        if not nodes:
            raise ValueError("subscription snapshot contains no usable nodes")
        return result, await engine.apply_nodes(nodes)

    async def sync_text_and_apply(
        self, source: str, body: bytes, engine: SingBoxEngine,
    ) -> tuple[SyncResult, Generation]:
        result = self.sync_text(source, body)
        nodes = self.registry.list_nodes()
        if not nodes:
            raise ValueError("subscription snapshot contains no usable nodes")
        return result, await engine.apply_nodes(nodes)

    @staticmethod
    def _decode_entries(body: bytes) -> list[str]:
        text = body.decode("utf-8", errors="strict").strip()
        entries = [line.strip() for line in text.splitlines() if line.strip()]
        schemes = {"vless", "trojan", "vmess", "ss"}
        if any("//" in line and line.split(":", 1)[0].lower() in schemes for line in entries):
            return entries
        try:
            decoded = base64.b64decode(text, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeError, ValueError):
            return entries
        return [line.strip() for line in decoded.splitlines() if line.strip()]
