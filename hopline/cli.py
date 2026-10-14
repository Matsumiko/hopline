from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
from pathlib import Path
from urllib.parse import urlsplit

from .registry import SQLiteRegistry
from .syncer import Syncer

DEFAULT_DB = "hopline.db"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hopline", description="Local Hopline egress proxy controls")
    subparsers = parser.add_subparsers(dest="command", required=True)

    for name, help_text in (
        ("sync", "Fetch and persist subscription nodes"),
        ("test", "Fetch and parse a subscription without starting sing-box"),
    ):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("--url", default=os.environ.get("HOPLINE_SUBSCRIPTION_URL"), help="subscription URL")
        sub.add_argument("--db", default=DEFAULT_DB, help="SQLite registry path")
        sub.add_argument("--json", action="store_true", dest="as_json", help="emit JSON only")

    doctor = subparsers.add_parser("doctor", help="Check local Hopline prerequisites")
    doctor.add_argument("--db", default=DEFAULT_DB, help="SQLite registry path")
    doctor.add_argument("--json", action="store_true", dest="as_json", help="emit JSON only")
    return parser


def _require_url(url: str | None) -> str:
    if not url:
        raise ValueError("subscription URL is required via --url or HOPLINE_SUBSCRIPTION_URL")
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("subscription URL must be an HTTP(S) URL")
    return url


def _emit(payload: dict[str, object], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        return
    for key, value in payload.items():
        print(f"{key}: {value}")


async def _sync(url: str, database: str) -> dict[str, object]:
    registry = SQLiteRegistry(database)
    try:
        result = await Syncer(registry).sync_url(url)
        return {
            "changed": result.changed,
            "invalid_entries": result.invalid_entries,
            "nodes": result.parsed_nodes,
            "not_modified": result.not_modified,
            "status": result.status,
            "used_last_valid": result.used_last_valid,
        }
    finally:
        registry.close()


def _doctor(database: str) -> dict[str, object]:
    binary = shutil.which("sing-box")
    db_path = Path(database)
    registry = SQLiteRegistry(database)
    try:
        nodes = len(registry.list_nodes())
        schema = registry.schema_version()
    finally:
        registry.close()
    return {
        "database": str(db_path),
        "database_exists": db_path.exists(),
        "nodes": nodes,
        "schema_version": schema,
        "sing_box": binary is not None,
        "sing_box_path": binary or "",
    }


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "doctor":
            payload = _doctor(args.db)
            _emit(payload, args.as_json)
            return 0 if payload["sing_box"] else 2
        url = _require_url(args.url)
        payload = asyncio.run(_sync(url, args.db))
        _emit(payload, args.as_json)
        return 0 if payload["nodes"] else 2
    except (OSError, ValueError, RuntimeError) as error:
        print(f"hopline: {error}", file=sys.stderr)
        return 2
