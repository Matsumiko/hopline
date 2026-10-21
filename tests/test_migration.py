import sqlite3
import tempfile
import unittest
from pathlib import Path

from hopline.registry import SQLiteRegistry


def _schema_version(connection: sqlite3.Connection) -> int:
    return int(connection.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0])


class MigrationTests(unittest.TestCase):
    def test_fresh_database_reaches_current_version(self) -> None:
        registry = SQLiteRegistry(":memory:")
        try:
            self.assertEqual(registry.schema_version(), SQLiteRegistry.SCHEMA_VERSION)
            health = {row[1] for row in registry.connection.execute("PRAGMA table_info(health)")}
            for column in ("conn_successes", "conn_failures", "latency_ewma_ms", "failure_category"):
                self.assertIn(column, health)
        finally:
            registry.close()

    def test_v1_database_upgrades_in_place_without_data_loss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "legacy.db"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO metadata(key, value) VALUES ('schema_version', '1');
                CREATE TABLE nodes (
                    id TEXT PRIMARY KEY, protocol TEXT NOT NULL, server TEXT NOT NULL,
                    port INTEGER NOT NULL, uuid TEXT NOT NULL, tls INTEGER NOT NULL,
                    sni TEXT, transport_type TEXT, name TEXT
                );
                CREATE TABLE subscriptions (source TEXT PRIMARY KEY, snapshot_hash TEXT NOT NULL, valid INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE node_sources (
                    node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                    source TEXT NOT NULL REFERENCES subscriptions(source) ON DELETE CASCADE,
                    PRIMARY KEY(node_id, source)
                );
                CREATE TABLE node_removals (
                    node_id TEXT NOT NULL, source TEXT NOT NULL, missing_syncs INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(node_id, source)
                );
                CREATE TABLE geolocation (
                    node_id TEXT PRIMARY KEY, ip TEXT NOT NULL, country_code TEXT NOT NULL,
                    country TEXT, asn TEXT, organization TEXT, provider TEXT NOT NULL,
                    checked_at REAL NOT NULL
                );
                CREATE TABLE health (
                    node_id TEXT PRIMARY KEY, state TEXT NOT NULL,
                    successes INTEGER NOT NULL DEFAULT 0, failures INTEGER NOT NULL DEFAULT 0,
                    latency_ms REAL, last_error TEXT, updated_at REAL NOT NULL
                );
                INSERT INTO subscriptions(source, snapshot_hash) VALUES ('legacy', 'abc');
                INSERT INTO nodes(id, protocol, server, port, uuid, tls, name)
                    VALUES ('node-a', 'vless', 'edge.test', 443, 'secret', 1, 'legacy node');
                INSERT INTO health(node_id, state, successes, failures, updated_at)
                    VALUES ('node-a', 'healthy', 7, 2, 1.0);
                """
            )
            connection.commit()
            connection.close()

            registry = SQLiteRegistry(str(path))
            try:
                self.assertEqual(registry.schema_version(), SQLiteRegistry.SCHEMA_VERSION)
                self.assertEqual(len(registry.list_nodes()), 1, "existing nodes must survive migration")
                record = registry.health_record("node-a")
                self.assertEqual(record.successes, 7)
                self.assertEqual(record.failures, 2)
                self.assertEqual(record.conn_successes, 0)
                self.assertIsNone(record.failure_category)
            finally:
                registry.close()

    def test_newer_schema_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "future.db"
            connection = sqlite3.connect(path)
            connection.execute("CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT INTO metadata(key, value) VALUES ('schema_version', '999')")
            connection.commit()
            connection.close()
            with self.assertRaises(RuntimeError):
                SQLiteRegistry(str(path))

    def test_migration_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "repeat.db"
            registry = SQLiteRegistry(str(path))
            try:
                first = registry.schema_version()
                self.assertEqual(registry.migrate_to_latest(), first)
                self.assertEqual(registry.migrate_to_latest(), first)
            finally:
                registry.close()
            reopened = SQLiteRegistry(str(path))
            try:
                self.assertEqual(reopened.schema_version(), first)
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
