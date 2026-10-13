from __future__ import annotations

import asyncio
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class FetchResult:
    url: str
    status: int
    body: bytes | None
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False


class SubscriptionFetcher:
    def __init__(
        self,
        *,
        timeout: float = 20.0,
        max_body_bytes: int = 2 * 1024 * 1024,
        user_agent: str = "hopline/0.1",
    ) -> None:
        if timeout <= 0 or max_body_bytes < 1 or not user_agent:
            raise ValueError("fetch limits and user agent must be valid")
        self.timeout = timeout
        self.max_body_bytes = max_body_bytes
        self.user_agent = user_agent

    async def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        return await asyncio.to_thread(self._fetch_blocking, url, etag, last_modified)

    def _fetch_blocking(
        self,
        url: str,
        etag: str | None,
        last_modified: str | None,
    ) -> FetchResult:
        request = urllib.request.Request(url, method="GET")
        request.add_header("User-Agent", self.user_agent)
        request.add_header("Accept", "*/*")
        if etag:
            request.add_header("If-None-Match", etag)
        if last_modified:
            request.add_header("If-Modified-Since", last_modified)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read(self.max_body_bytes + 1)
                if len(body) > self.max_body_bytes:
                    raise ValueError("subscription response exceeds configured limit")
                return FetchResult(
                    url=url,
                    status=response.status,
                    body=body,
                    etag=response.headers.get("ETag"),
                    last_modified=response.headers.get("Last-Modified"),
                )
        except urllib.error.HTTPError as error:
            if error.code == 304:
                return FetchResult(url=url, status=304, body=None, not_modified=True)
            raise

    @staticmethod
    def redacted_headers(headers: Mapping[str, str]) -> dict[str, str]:
        return {
            key: "<present>"
            for key in headers
            if key.lower() in {"etag", "last-modified"}
        }
