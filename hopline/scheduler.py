from __future__ import annotations

import asyncio
import random
from collections.abc import Callable, Sequence

from .engine import SingBoxEngine
from .generation import Generation
from .syncer import SyncResult, Syncer


class SubscriptionScheduler:
    def __init__(
        self,
        syncer: Syncer,
        sources: Sequence[str],
        *,
        static_nodes: Sequence[str] = (),
        engine: SingBoxEngine | None = None,
        on_generation: Callable[[Generation], None] | None = None,
        interval: float = 45 * 60,
        jitter: float = 0,
    ) -> None:
        if not sources and not static_nodes:
            raise ValueError("at least one subscription source or static node is required")
        if interval <= 0 or jitter < 0 or jitter >= interval:
            raise ValueError("scheduler interval and jitter are invalid")
        self.syncer = syncer
        self.sources = tuple(sources)
        self.static_nodes = tuple(static_nodes)
        self.engine = engine
        self.on_generation = on_generation
        self.interval = interval
        self.jitter = jitter
        self._stop = asyncio.Event()
        self._sync_lock = asyncio.Lock()

    async def sync_once(self) -> list[SyncResult]:
        async with self._sync_lock:
            return await self._sync_once_impl()

    async def sync_now(self) -> list[SyncResult]:
        return await self.sync_once()

    async def _sync_once_impl(self) -> list[SyncResult]:
        results: list[SyncResult] = []
        completed = True
        registry = getattr(self.syncer, "registry", None)
        if registry is not None:
            sources = tuple(registry.list_managed_subscriptions())
        else:
            sources = tuple(self.sources)
        for source in sources:
            if self._stop.is_set():
                completed = False
                break
            if self.engine is None:
                results.append(await self.syncer.sync_url(source))
            else:
                # Fetch/parse only; a single generation is published after every source
                # has been reconciled so intermediate snapshots never trigger a swap.
                result = await self.syncer.sync_url(source)
                results.append(result)
        for link in self.static_nodes:
            if self._stop.is_set():
                completed = False
                break
            if self.engine is None:
                results.append(self.syncer.sync_static(link))
            else:
                results.append(self.syncer.sync_static(link))
        registry = getattr(self.syncer, "registry", None)
        if completed and registry is not None:
            if self.engine is not None:
                nodes = registry.list_nodes()
                if nodes:
                    generation = await self.engine.apply_nodes(nodes)
                    if self.on_generation is not None:
                        self.on_generation(generation)
            registry.reconcile_subscription_sources(sources)
            if self.engine is not None and registry.snapshot_ids() != tuple(node.id for node in nodes):
                remaining = registry.list_nodes()
                if remaining:
                    generation = await self.engine.apply_nodes(remaining)
                    if self.on_generation is not None:
                        self.on_generation(generation)
        return results

    async def run(self, *, initial_sync: bool = True) -> None:
        if initial_sync:
            await self.sync_once()
        while not self._stop.is_set():
            delay = self.interval + random.uniform(-self.jitter, self.jitter)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=max(0, delay))
            except asyncio.TimeoutError:
                await self.sync_once()

    def stop(self) -> None:
        self._stop.set()
