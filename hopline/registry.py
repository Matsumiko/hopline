from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable

from .models import Node


class SQLiteRegistry:
    def __init__(self, database: str | sqlite3.Connection) -> None:
        self.connection = (
            sqlite3.connect(database)
            if isinstance(database, str)
            else database
        )
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
                name TEXT
            );
            CREATE TABLE IF NOT EXISTS subscriptions (
                source TEXT PRIMARY KEY,
                snapshot_hash TEXT NOT NULL,
                valid INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS node_sources (
                node_id TEXT NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
                source TEXT NOT NULL REFERENCES subscriptions(source) ON DELETE CASCADE,
                PRIMARY KEY(node_id, source)
            );
            """
        )
        self.connection.commit()

    def schema_version(self) -> int:
        row = self.connection.execute(
            "SELECT value FROM metadata WHERE key = 'schema_version'"
        ).fetchone()
        if row is None:
            raise RuntimeError("registry schema version is missing")
        return int(row[0])

    def list_nodes(self) -> list[Node]:
        rows = self.connection.execute(
            "SELECT id, protocol, server, port, uuid, tls, sni, transport_type, path, host, name "
            "FROM nodes ORDER BY id"
        ).fetchall()
        return [self._node_from_row(row) for row in rows]

    def snapshot_ids(self) -> tuple[str, ...]:
        return tuple(row[0] for row in self.connection.execute("SELECT id FROM nodes ORDER BY id"))

    def replace_subscription(
        self,
        source: str,
        snapshot_hash: str,
        nodes: Iterable[Node],
    ) -> bool:
        if not source:
            raise ValueError("subscription source is required")
        incoming = {node.id: node for node in nodes}
        before = self.snapshot_ids()
        with self.connection:
            self.connection.execute(
                "INSERT INTO subscriptions(source, snapshot_hash, valid) VALUES (?, ?, 1) "
                "ON CONFLICT(source) DO UPDATE SET snapshot_hash=excluded.snapshot_hash, valid=1, updated_at=CURRENT_TIMESTAMP",
                (source, snapshot_hash),
            )
            old_ids = {
                row[0]
                for row in self.connection.execute(
                    "SELECT node_id FROM node_sources WHERE source = ?", (source,)
                )
            }
            for node in incoming.values():
                self.connection.execute(
                    """INSERT INTO nodes(
                        id, protocol, server, port, uuid, tls, sni, transport_type, path, host, name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        protocol=excluded.protocol, server=excluded.server, port=excluded.port,
                        uuid=excluded.uuid, tls=excluded.tls, sni=excluded.sni,
                        transport_type=excluded.transport_type, path=excluded.path,
                        host=excluded.host, name=excluded.name""",
                    (
                        node.id, node.protocol, node.server, node.port, node.uuid,
                        int(node.tls), node.sni, node.transport_type, node.path,
                        node.host, node.name,
                    ),
                )
                self.connection.execute(
                    "INSERT OR IGNORE INTO node_sources(node_id, source) VALUES (?, ?)",
                    (node.id, source),
                )
            if old_ids:
                placeholders = ",".join("?" for _ in old_ids)
                self.connection.execute(
                    f"DELETE FROM node_sources WHERE source = ? AND node_id IN ({placeholders})",
                    (source, *old_ids),
                )
                for node_id in incoming:
                    self.connection.execute(
                        "INSERT OR IGNORE INTO node_sources(node_id, source) VALUES (?, ?)",
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
            id=row["id"], protocol=row["protocol"], server=row["server"],
            port=row["port"], uuid=row["uuid"], tls=bool(row["tls"]),
            sni=row["sni"], transport_type=row["transport_type"],
            path=row["path"], host=row["host"], name=row["name"],
        )
