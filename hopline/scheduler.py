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
        engine: SingBoxEngine | None = None,
        on_generation: Callable[[Generation], None] | None = None,
        interval: float = 45 * 60,
        jitter: float = 0,
    ) -> None:
        if not sources:
            raise ValueError("at least one subscription source is required")
        if interval <= 0 or jitter < 0 or jitter >= interval:
            raise ValueError("scheduler interval and jitter are invalid")
        self.syncer = syncer
        self.sources = tuple(sources)
        self.engine = engine
        self.on_generation = on_generation
        self.interval = interval
        self.jitter = jitter
        self._stop = asyncio.Event()

    async def sync_once(self) -> list[SyncResult]:
        results: list[SyncResult] = []
        for source in self.sources:
            if self._stop.is_set():
                break
            if self.engine is None:
                results.append(await self.syncer.sync_url(source))
            else:
                result, generation = await self.syncer.sync_url_and_apply(source, self.engine)
                if self.on_generation is not None:
                    self.on_generation(generation)
                results.append(result)
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
