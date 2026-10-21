import asyncio
import base64
import shutil
import sqlite3
import tempfile
import unittest
from pathlib import Path
from hopline.models import Node
from hopline.registry import SQLiteRegistry
from hopline.syncer import Syncer


VALID_A = "vless://00000000-0000-4000-8000-000000000001@a.example.test:443?security=tls&sni=a.example.test&type=ws&path=%2Fa#A"
VALID_B = "vless://00000000-0000-4000-8000-000000000002@b.example.test:443?security=tls&sni=b.example.test&type=ws&path=%2Fb#B"


class SyncerRegistryTests(unittest.TestCase):
    def test_sync_deduplicates_invalid_entries_and_persists_nodes(self) -> None:
        registry = SQLiteRegistry(":memory:")
        syncer = Syncer(registry, max_body_bytes=4096, max_nodes=10)

        result = syncer.sync_text(
            "sub-a",
            f"{VALID_A}\nnot-a-node\n{VALID_A}\n{VALID_B}".encode(),
        )

        self.assertTrue(result.changed)
        self.assertEqual(result.parsed_nodes, 2)
        self.assertEqual(result.invalid_entries, 1)
        self.assertEqual([node.server for node in registry.list_nodes()], ["a.example.test", "b.example.test"])

    def test_same_snapshot_is_noop(self) -> None:
        registry = SQLiteRegistry(":memory:")
        syncer = Syncer(registry)
        body = f"{VALID_A}\n{VALID_B}".encode()

        first = syncer.sync_text("sub-a", body)
        second = syncer.sync_text("sub-a", body)

        self.assertTrue(first.changed)
        self.assertFalse(second.changed)
        self.assertEqual(second.parsed_nodes, 2)

    def test_base64_snapshot_and_last_valid_nodes(self) -> None:
        registry = SQLiteRegistry(":memory:")
        syncer = Syncer(registry)
        encoded = base64.b64encode(VALID_A.encode())

        first = syncer.sync_text("sub-a", encoded)
        fallback = syncer.sync_text("sub-a", b"broken-content")

        self.assertTrue(first.changed)
        self.assertFalse(fallback.changed)
        self.assertTrue(fallback.used_last_valid)
        self.assertEqual([node.server for node in registry.list_nodes()], ["a.example.test"])

    @unittest.skipUnless(shutil.which("sing-box"), "sing-box is required")
    def test_sync_text_and_apply_reuses_generation(self) -> None:
        async def scenario() -> None:
            from hopline.engine import SingBoxEngine

            registry = SQLiteRegistry(":memory:")
            syncer = Syncer(registry)
            engine = SingBoxEngine(base_port=18974)
            try:
                first, generation = await syncer.sync_text_and_apply("sub-a", VALID_A.encode(), engine)
                second, same_generation = await syncer.sync_text_and_apply("sub-a", VALID_A.encode(), engine)
                self.assertTrue(first.changed)
                self.assertFalse(second.changed)
                self.assertIs(generation, same_generation)
            finally:
                await engine.close()

        asyncio.run(scenario())

    def test_health_write_survives_concurrent_read_transaction(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "hopline.db")
            registry = SQLiteRegistry(database)
            registry.replace_subscription(
                "fixture", "hash", [Node("node-a", "vless", "edge.test", 443, "secret")]
            )
            reader = sqlite3.connect(database)
            try:
                reader.execute("BEGIN")
                reader.execute("SELECT * FROM nodes").fetchall()
                record = registry.save_health("node-a", "healthy", 1, 0, 12.0, None)
                self.assertEqual(record.state.value, "healthy")
            finally:
                reader.rollback()
                reader.close()
                registry.close()


    def test_health_write_for_retired_node_is_ignored(self) -> None:
        registry = SQLiteRegistry(":memory:")
        self.assertIsNone(registry.save_health("retired", "dead", 1, 1, None, "timeout"))
        self.assertEqual(registry.list_health(), [])
        registry.close()
    def test_schema_is_created_on_connection(self) -> None:
        connection = sqlite3.connect(":memory:")
        registry = SQLiteRegistry(connection)
        self.assertEqual(registry.schema_version(), SQLiteRegistry.SCHEMA_VERSION)


if __name__ == "__main__":
    unittest.main()
