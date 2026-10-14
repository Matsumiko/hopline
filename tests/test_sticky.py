import unittest

from hopline.sticky import StickySessionStore


class StickySessionStoreTests(unittest.TestCase):
    def test_binding_renews_only_when_successful_connection_binds(self) -> None:
        now = [100.0]
        store = StickySessionStore(ttl=10, clock=lambda: now[0])

        self.assertIsNone(store.lookup("job", eligible=lambda _node: True))
        store.bind("job", "node-a")
        self.assertEqual(store.lookup("job", eligible=lambda node: node == "node-a"), "node-a")
        now[0] = 109.9
        self.assertEqual(store.lookup("job", eligible=lambda _node: True), "node-a")
        now[0] = 110.1
        self.assertIsNone(store.lookup("job", eligible=lambda _node: True))

    def test_unavailable_binding_is_removed_for_rebind(self) -> None:
        store = StickySessionStore(ttl=10, clock=lambda: 100.0)
        store.bind("job", "node-a")

        self.assertIsNone(store.lookup("job", eligible=lambda _node: False))
        store.bind("job", "node-b")
        self.assertEqual(store.lookup("job", eligible=lambda node: node == "node-b"), "node-b")


if __name__ == "__main__":
    unittest.main()
