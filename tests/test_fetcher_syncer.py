import asyncio
import unittest

from hopline.fetcher import FetchResult
from hopline.registry import SQLiteRegistry
from hopline.syncer import Syncer


VLESS = "vless://00000000-0000-4000-8000-000000000011@a.example.test:443?security=tls&sni=a.example.test&type=ws&path=%2Fa#A"
TROJAN = "trojan://00000000-0000-4000-8000-000000000012@b.example.test:443?security=tls&sni=b.example.test&type=ws&path=%2Fb#B"
VMESS = "vmess://00000000-0000-4000-8000-000000000013@c.example.test:443?security=tls&sni=c.example.test&type=ws&path=%2Fc#C"
SS = "ss://bmVvbmNyeXB0OmZpeHR1cmUtcGFzcw==@d.example.test:443?security=tls&sni=d.example.test&type=ws&path=%2Fd#D"


class FakeFetcher:
    def __init__(self, result: FetchResult | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, str | None, str | None]] = []

    async def fetch(self, url: str, *, etag: str | None = None, last_modified: str | None = None) -> FetchResult:
        self.calls.append((url, etag, last_modified))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FetcherSyncerTests(unittest.TestCase):
    def test_sync_parses_all_subscription_protocols(self) -> None:
        syncer = Syncer(SQLiteRegistry(":memory:"))
        result = syncer.sync_text("fixture", f"{VLESS}\n{TROJAN}\n{VMESS}\n{SS}".encode())
        self.assertEqual(result.parsed_nodes, 4)
        self.assertEqual({node.protocol for node in syncer.registry.list_nodes()}, {"vless", "trojan", "vmess", "ss"})

    def test_sync_url_sends_saved_validators_and_persists_body(self) -> None:
        registry = SQLiteRegistry(":memory:")
        initial = FetchResult("fixture", 200, VLESS.encode(), etag="etag-1", last_modified="date-1")
        fetcher = FakeFetcher(initial)
        syncer = Syncer(registry, fetcher=fetcher)

        result = asyncio.run(syncer.sync_url("fixture"))
        metadata = registry.subscription_metadata("fixture")

        self.assertTrue(result.changed)
        self.assertEqual(metadata["body"], VLESS.encode())
        self.assertEqual(metadata["etag"], "etag-1")
        self.assertEqual(metadata["last_modified"], "date-1")

    def test_not_modified_is_noop(self) -> None:
        registry = SQLiteRegistry(":memory:")
        syncer = Syncer(registry, fetcher=FakeFetcher(FetchResult("fixture", 200, VLESS.encode(), etag="e")))
        asyncio.run(syncer.sync_url("fixture"))
        fetcher = FakeFetcher(FetchResult("fixture", 304, None, not_modified=True))
        syncer.fetcher = fetcher

        result = asyncio.run(syncer.sync_url("fixture"))

        self.assertTrue(result.not_modified)
        self.assertFalse(result.changed)
        self.assertEqual(fetcher.calls, [("fixture", "e", None)])

    def test_fetch_failure_uses_last_valid_registry(self) -> None:
        registry = SQLiteRegistry(":memory:")
        syncer = Syncer(registry, fetcher=FakeFetcher(FetchResult("fixture", 200, VLESS.encode())))
        asyncio.run(syncer.sync_url("fixture"))
        syncer.fetcher = FakeFetcher(OSError("temporary failure"))

        result = asyncio.run(syncer.sync_url("fixture"))

        self.assertTrue(result.used_last_valid)
        self.assertEqual(result.status, 0)
        self.assertEqual(len(registry.list_nodes()), 1)

    def test_redacted_headers_never_return_header_values(self) -> None:
        from hopline.fetcher import SubscriptionFetcher

        redacted = SubscriptionFetcher.redacted_headers({
            "ETag": "secret-validator",
            "Last-Modified": "private-date",
            "X-Irrelevant": "ignored",
        })
        self.assertEqual(redacted, {"ETag": "<present>", "Last-Modified": "<present>"})
        self.assertNotIn("secret-validator", str(redacted))
        self.assertNotIn("private-date", str(redacted))
if __name__ == "__main__":
    unittest.main()
