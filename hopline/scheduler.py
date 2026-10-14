from __future__ import annotations

import asyncio
import random
from collections.abc import Sequence

from .engine import SingBoxEngine
from .syncer import SyncResult, Syncer


class SubscriptionScheduler:
    def __init__(
        self,
        syncer: Syncer,
        sources: Sequence[str],
        *,
        engine: SingBoxEngine | None = None,
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
                result, _generation = await self.syncer.sync_url_and_apply(source, self.engine)
                results.append(result)
        return results

    async def run(self) -> None:
        while not self._stop.is_set():
            await self.sync_once()
            delay = self.interval + random.uniform(-self.jitter, self.jitter)
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=max(0, delay))
            except asyncio.TimeoutError:
                continue

    def stop(self) -> None:
        self._stop.set()
