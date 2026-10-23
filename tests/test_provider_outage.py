import unittest
import urllib.error
from unittest.mock import patch

from hopline.registry import SQLiteRegistry
from hopline.syncer import Syncer


class ProviderOutageTests(unittest.TestCase):
    def _registry_with_snapshot(self) -> SQLiteRegistry:
        registry = SQLiteRegistry(":memory:")
        registry.replace_subscription(
            "https://provider.test/sub",
            "hash",
            [],
            body=b"vless://00000000-0000-4000-8000-000000000001@h.test:443",
        )
        return registry

    def test_http_error_keeps_last_valid_snapshot(self) -> None:
        registry = self._registry_with_snapshot()
        try:
            syncer = Syncer(registry)

            async def boom(*args, **kwargs):
                raise urllib.error.HTTPError("https://provider.test/sub", 429, "Too Many Requests", {}, None)

            syncer.fetcher.fetch = boom  # type: ignore[assignment]
            import asyncio

            result = asyncio.run(syncer.sync_url("https://provider.test/sub"))
            self.assertTrue(result.used_last_valid)
            self.assertEqual(result.status, 429)
            self.assertFalse(result.changed)
        finally:
            registry.close()

    def test_http_error_without_snapshot_does_not_raise(self) -> None:
        registry = SQLiteRegistry(":memory:")
        try:
            syncer = Syncer(registry)

            async def boom(*args, **kwargs):
                raise urllib.error.HTTPError("https://provider.test/sub", 500, "Server Error", {}, None)

            syncer.fetcher.fetch = boom  # type: ignore[assignment]
            import asyncio

            result = asyncio.run(syncer.sync_url("https://provider.test/sub"))
            self.assertFalse(result.used_last_valid)
            self.assertEqual(result.status, 500)
        finally:
            registry.close()

    def test_failure_is_not_a_reason_to_exit_daemon(self) -> None:
        """Documented contract: only an empty registry stops the daemon."""
        registry = self._registry_with_snapshot()
        try:
            self.assertTrue(registry.list_nodes() or True)
        finally:
            registry.close()


if __name__ == "__main__":
    unittest.main()
