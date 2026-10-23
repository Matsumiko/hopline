import unittest

from hopline.registry import SQLiteRegistry
from hopline.scheduler import SubscriptionScheduler
from hopline.syncer import SyncResult


class SubscriptionSeedTests(unittest.TestCase):
    def test_seed_imports_config_urls_exactly_once(self) -> None:
        registry = SQLiteRegistry(":memory:")
        try:
            self.assertTrue(registry.seed_managed_subscriptions_once(["https://a.test/sub"]))
            self.assertEqual(registry.list_managed_subscriptions(), ["https://a.test/sub"])

            # Deleting via the panel must survive a restart, so a second seed is a no-op.
            registry.remove_subscription("https://a.test/sub")
            self.assertFalse(registry.seed_managed_subscriptions_once(["https://a.test/sub"]))
            self.assertEqual(registry.list_managed_subscriptions(), [])
        finally:
            registry.close()

    def test_db_wins_over_config_after_first_seed(self) -> None:
        registry = SQLiteRegistry(":memory:")
        try:
            registry.seed_managed_subscriptions_once(["https://config.test/a"])
            registry.add_managed_subscription("https://panel.test/b")
            registry.seed_managed_subscriptions_once(["https://config.test/a", "https://config.test/new"])
            self.assertEqual(
                registry.list_managed_subscriptions(),
                ["https://config.test/a", "https://panel.test/b"],
                "config must not add or resurrect sources after the first seed",
            )
        finally:
            registry.close()

    def test_scheduler_runs_from_registry_sources_only(self) -> None:
        registry = SQLiteRegistry(":memory:")
        try:
            registry.add_managed_subscription("https://db.test/sub")
            seen: list[str] = []

            class FakeSyncer:
                def __init__(self) -> None:
                    self.registry = registry

                async def sync_url(self, url: str) -> SyncResult:
                    seen.append(url)
                    return SyncResult(url, True, 1, 0, False)

            scheduler = SubscriptionScheduler(FakeSyncer(), [], interval=60, jitter=0)
            results = scheduler.sync_once_result = __import__("asyncio").run(scheduler.sync_once())
            self.assertEqual(seen, ["https://db.test/sub"])
            self.assertEqual(len(results), 1)
        finally:
            registry.close()

    def test_scheduler_rejects_empty_db_and_empty_config(self) -> None:
        registry = SQLiteRegistry(":memory:")
        try:
            class FakeSyncer:
                def __init__(self) -> None:
                    self.registry = registry

            with self.assertRaises(ValueError):
                SubscriptionScheduler(FakeSyncer(), [], interval=60, jitter=0)
        finally:
            registry.close()


if __name__ == "__main__":
    unittest.main()
