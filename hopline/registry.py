from __future__ import annotations

import sqlite3
from collections.abc import Iterable

from .models import Node


class SQLiteRegistry:
    def __init__(self, database: str | sqlite3.Connection) -> None:
        self.connection = sqlite3.connect(database) if isinstance(database, str) else database
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def _create_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            INSERT OR IGNORE INTO metadata(key, value) VALUES ('schema_version', '1');
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                protocol TEXT NOT NULL,
                server TEXT NOT NULL,
                port INTEGER NOT NULL,
                uuid TEXT NOT NULL,
                tls INTEGER NOT NULL,
                sni TEXT,
                transport_type TEXT,
                path TEXT,
                host TEXT,
                method TEXT,
                plugin TEXT,
                plugin_opts TEXT,
                security TEXT,
                global_padding INTEGER,
                authenticated_length INTEGER,
                name TEXT
            );
            CREATE TABLE IF NOT EXISTS subscriptions (
                source TEXT PRIMARY KEY,
                snapshot_hash TEXT NOT NULL,
                valid INTEGER NOT NULL DEFAULT 1,
                body BLOB,
                etag TEXT,
                last_modified TEXT,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS node_sources (
                node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                source TEXT NOT NULL REFERENCES subscriptions(source) ON DELETE CASCADE,
                PRIMARY KEY(node_id, source)
            );
            CREATE TABLE IF NOT EXISTS node_removals (
                node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                source TEXT NOT NULL REFERENCES subscriptions(source) ON DELETE CASCADE,
                missing_syncs INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(node_id, source)
            );
            CREATE TABLE IF NOT EXISTS health (
                node_id TEXT PRIMARY KEY REFERENCES nodes(id) ON DELETE CASCADE,
                state TEXT NOT NULL,
                successes INTEGER NOT NULL DEFAULT 0,
                failures INTEGER NOT NULL DEFAULT 0,
                latency_ms REAL,
                last_error TEXT,
                updated_at REAL NOT NULL
            );
            """
        )
        self._ensure_columns()
        self.connection.commit()

    def _ensure_columns(self) -> None:
        tables = {
            "nodes": {row[1] for row in self.connection.execute("PRAGMA table_info(nodes)")},
            "subscriptions": {row[1] for row in self.connection.execute("PRAGMA table_info(subscriptions)")},
        }
        node_columns = (
            ("path", "TEXT"), ("host", "TEXT"), ("method", "TEXT"),
            ("plugin", "TEXT"), ("plugin_opts", "TEXT"), ("security", "TEXT"),
            ("global_padding", "INTEGER"), ("authenticated_length", "INTEGER"),
        )
        for name, definition in node_columns:
            if name not in tables["nodes"]:
                self.connection.execute(f"ALTER TABLE nodes ADD COLUMN {name} {definition}")
        for name, definition in (("body", "BLOB"), ("etag", "TEXT"), ("last_modified", "TEXT")):
            if name not in tables["subscriptions"]:
                self.connection.execute(f"ALTER TABLE subscriptions ADD COLUMN {name} {definition}")

    def schema_version(self) -> int:
        row = self.connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            raise RuntimeError("registry schema version is missing")
        return int(row[0])

    def list_nodes(self) -> list[Node]:
        rows = self.connection.execute(
            "SELECT id, protocol, server, port, uuid, tls, sni, transport_type, path, host, method, "
            "plugin, plugin_opts, security, global_padding, authenticated_length, name "
            "FROM nodes ORDER BY id"
        ).fetchall()
        return [self._node_from_row(row) for row in rows]

    def health_record(self, node_id: str):
        from .health import HealthRecord, HealthState

        row = self.connection.execute(
            "SELECT node_id, state, successes, failures, latency_ms, last_error, updated_at FROM health WHERE node_id = ?",
            (node_id,),
        ).fetchone()
        if row is None:
            return None
        return HealthRecord(
            row["node_id"], HealthState(row["state"]), row["successes"],
            row["failures"], row["latency_ms"], row["last_error"], row["updated_at"],
        )

    def save_health(self, node_id: str, state, successes: int, failures: int, latency_ms: float | None, last_error: str | None):
        import time

        updated_at = time.time()
        with self.connection:
            self.connection.execute(
                """INSERT INTO health(node_id, state, successes, failures, latency_ms, last_error, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET state=excluded.state, successes=excluded.successes,
                failures=excluded.failures, latency_ms=excluded.latency_ms, last_error=excluded.last_error,
                updated_at=excluded.updated_at""",
                (node_id, str(state), successes, failures, latency_ms, last_error, updated_at),
            )
        return self.health_record(node_id)

    def list_health(self):
        return [self.health_record(row[0]) for row in self.connection.execute("SELECT node_id FROM health ORDER BY node_id")]

    def snapshot_ids(self) -> tuple[str, ...]:
        return tuple(row[0] for row in self.connection.execute("SELECT id FROM nodes ORDER BY id"))

    def subscription_metadata(self, source: str) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT source, snapshot_hash, valid, body, etag, last_modified FROM subscriptions WHERE source = ?",
            (source,),
        ).fetchone()

    def replace_subscription(
        self,
        source: str,
        snapshot_hash: str,
        nodes: Iterable[Node],
        *,
        body: bytes | None = None,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> bool:
        if not source:
            raise ValueError("subscription source is required")
        incoming = {node.id: node for node in nodes}
        before = self.snapshot_ids()
        with self.connection:
            self.connection.execute(
                """INSERT INTO subscriptions(source, snapshot_hash, valid, body, etag, last_modified)
                VALUES (?, ?, 1, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET snapshot_hash=excluded.snapshot_hash,
                valid=1, body=COALESCE(excluded.body, subscriptions.body),
                etag=excluded.etag, last_modified=excluded.last_modified,
                updated_at=CURRENT_TIMESTAMP""",
                (source, snapshot_hash, body, etag, last_modified),
            )
            old_ids = {
                row[0] for row in self.connection.execute(
                    "SELECT node_id FROM node_sources WHERE source = ?", (source,)
                )
            }
            for node in incoming.values():
                self.connection.execute(
                    """INSERT INTO nodes(
                        id, protocol, server, port, uuid, tls, sni, transport_type, path, host, method,
                        plugin, plugin_opts, security, global_padding, authenticated_length, name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET protocol=excluded.protocol, server=excluded.server,
                    port=excluded.port, uuid=excluded.uuid, tls=excluded.tls, sni=excluded.sni,
                    transport_type=excluded.transport_type, path=excluded.path, host=excluded.host,
                    method=excluded.method, plugin=excluded.plugin, plugin_opts=excluded.plugin_opts,
                    security=excluded.security, global_padding=excluded.global_padding,
                    authenticated_length=excluded.authenticated_length, name=excluded.name""",
                    (
                        node.id, node.protocol, node.server, node.port, node.uuid, int(node.tls),
                        node.sni, node.transport_type, node.path, node.host, node.method,
                        node.plugin, node.plugin_opts, node.security,
                        None if node.global_padding is None else int(node.global_padding),
                        None if node.authenticated_length is None else int(node.authenticated_length),
                        node.name,
                    ),
                )
                self.connection.execute(
                    "INSERT OR IGNORE INTO node_sources(node_id, source) VALUES (?, ?)",
                    (node.id, source),
                )
            for node_id in old_ids - incoming.keys():
                row = self.connection.execute(
                    "SELECT missing_syncs FROM node_removals WHERE node_id = ? AND source = ?",
                    (node_id, source),
                ).fetchone()
                missing = (row[0] if row else 0) + 1
                if missing >= 3:
                    self.connection.execute(
                        "DELETE FROM node_sources WHERE node_id = ? AND source = ?",
                        (node_id, source),
                    )
                    self.connection.execute(
                        "DELETE FROM node_removals WHERE node_id = ? AND source = ?",
                        (node_id, source),
                    )
                else:
                    self.connection.execute(
                        "INSERT INTO node_removals(node_id, source, missing_syncs) VALUES (?, ?, ?) "
                        "ON CONFLICT(node_id, source) DO UPDATE SET missing_syncs=excluded.missing_syncs",
                        (node_id, source, missing),
                    )
            for node_id in incoming:
                self.connection.execute(
                    "DELETE FROM node_removals WHERE node_id = ? AND source = ?",
                    (node_id, source),
                )
            self.connection.execute(
                "DELETE FROM nodes WHERE id NOT IN (SELECT node_id FROM node_sources)"
            )
        return before != self.snapshot_ids()

    def close(self) -> None:
        self.connection.close()

    @staticmethod
    def _node_from_row(row: sqlite3.Row) -> Node:
        return Node(
            id=row["id"], protocol=row["protocol"], server=row["server"], port=row["port"],
            uuid=row["uuid"], tls=bool(row["tls"]), sni=row["sni"],
            transport_type=row["transport_type"], path=row["path"], host=row["host"],
            method=row["method"], plugin=row["plugin"], plugin_opts=row["plugin_opts"],
            security=row["security"],
            global_padding=None if row["global_padding"] is None else bool(row["global_padding"]),
            authenticated_length=None if row["authenticated_length"] is None else bool(row["authenticated_length"]),
            name=row["name"],
        )
