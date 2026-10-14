from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import sys
from pathlib import Path
from urllib.parse import urlsplit

from .config import HoplineConfig
from .registry import SQLiteRegistry
from .scheduler import SubscriptionScheduler
from .syncer import Syncer

DEFAULT_DB = "hopline.db"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="hopline", description="Local Hopline egress proxy controls")
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (("sync", "Fetch and persist subscription nodes"), ("test", "Fetch and parse a subscription without starting sing-box")):
        sub = subparsers.add_parser(name, help=help_text)
        sub.add_argument("--url", default=os.environ.get("HOPLINE_SUBSCRIPTION_URL"), help="subscription URL")
        sub.add_argument("--db", default=DEFAULT_DB, help="SQLite registry path")
        sub.add_argument("--json", action="store_true", dest="as_json", help="emit JSON only")
    doctor = subparsers.add_parser("doctor", help="Check local Hopline prerequisites")
    doctor.add_argument("--db", default=DEFAULT_DB, help="SQLite registry path")
    doctor.add_argument("--json", action="store_true", dest="as_json", help="emit JSON only")
    for name in ("status", "nodes"):
        sub = subparsers.add_parser(name, help=f"Read control API {name}")
        sub.add_argument("--host", default="127.0.0.1")
        sub.add_argument("--port", type=int, default=18772)
        sub.add_argument("--json", action="store_true", dest="as_json")
    run = subparsers.add_parser("run", help="Run the subscription scheduler")
    run.add_argument("--config", default=os.environ.get("HOPLINE_CONFIG", "hopline.toml"), help="TOML config path")
    run.add_argument("--once", action="store_true", help="sync once then exit")
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
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")


async def _sync(url: str, database: str) -> dict[str, object]:
    registry = SQLiteRegistry(database)
    try:
        result = await Syncer(registry).sync_url(url)
        return {"changed": result.changed, "invalid_entries": result.invalid_entries, "nodes": result.parsed_nodes, "not_modified": result.not_modified, "status": result.status, "used_last_valid": result.used_last_valid}
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
    return {"database": str(db_path), "database_exists": db_path.exists(), "nodes": nodes, "schema_version": schema, "sing_box": binary is not None, "sing_box_path": binary or ""}


async def _control_request(host: str, port: int, path: str) -> dict[str, object]:
    reader, writer = await asyncio.open_connection(host, port)
    try:
        writer.write(f"GET {path} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode())
        await writer.drain()
        response = await reader.read()
        header, body = response.split(b"\r\n\r\n", 1)
        status = int(header.split(b" ", 2)[1])
        if status != 200:
            raise RuntimeError(f"control API returned HTTP {status}")
        return json.loads(body)
    finally:
        writer.close()
        await writer.wait_closed()


async def _run_daemon(config_path: str, once: bool) -> int:
    from .control import ControlServer
    from .health import HealthChecker
    from .probe import ActiveProbeScheduler

    config = HoplineConfig.from_file(config_path)
    registry = SQLiteRegistry(config.database)
    scheduler = SubscriptionScheduler(Syncer(registry), config.subscriptions, interval=config.interval, jitter=config.jitter)
    probe_scheduler = None
    probe_task = None
    if config.probe_targets:
        probe_scheduler = ActiveProbeScheduler(
            HealthChecker(registry), registry.list_nodes, config.probe_targets,
            interval=config.probe_interval, timeout=config.probe_timeout,
        )
        probe_task = asyncio.create_task(probe_scheduler.run())
    control = ControlServer(registry)
    await control.start()
    loop = asyncio.get_running_loop()

    def stop_all() -> None:
        scheduler.stop()
        if probe_scheduler is not None:
            probe_scheduler.stop()

    for signal_name in ("SIGINT", "SIGTERM"):
        signal_number = getattr(signal, signal_name, None)
        if signal_number is not None:
            loop.add_signal_handler(signal_number, stop_all)
    try:
        if once:
            results = await scheduler.sync_once()
            if probe_scheduler is not None:
                await probe_scheduler.probe_once()
            print(json.dumps({"sources": len(results), "nodes": len(registry.list_nodes()), "probes": len(probe_scheduler.targets) if probe_scheduler else 0, "control_port": control.port, "once": True}, sort_keys=True))
            return 0 if results and registry.list_nodes() else 2
        await scheduler.run()
        return 0
    finally:
        if probe_scheduler is not None:
            probe_scheduler.stop()
        if probe_task is not None:
            probe_task.cancel()
            await asyncio.gather(probe_task, return_exceptions=True)
        await control.stop()
        registry.close()


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "run":
            return asyncio.run(_run_daemon(args.config, args.once))
        if args.command == "doctor":
            payload = _doctor(args.db)
            _emit(payload, args.as_json)
            return 0 if payload["sing_box"] else 2
        if args.command in {"status", "nodes"}:
            payload = asyncio.run(_control_request(args.host, args.port, "/" + args.command))
            _emit(payload, args.as_json)
            return 0
        url = _require_url(args.url)
        payload = asyncio.run(_sync(url, args.db))
        _emit(payload, args.as_json)
        return 0 if payload["nodes"] else 2
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"hopline: {error}", file=sys.stderr)
        return 2
