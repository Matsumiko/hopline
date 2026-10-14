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
from .engine import SingBoxEngine
from .gateway import Gateway
from .geolocation import GeolocationResolver, fetch_exit_ip
from .health import HealthChecker
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
    geo = subparsers.add_parser("geo", help="Resolve the exit IP and country of one node")
    geo.add_argument("--config", default=os.environ.get("HOPLINE_CONFIG", "hopline.toml"), help="TOML config path")
    geo.add_argument("--node", required=True, help="node ID to test")
    geo.add_argument("--exit-ip-url", default="https://api.ipify.org?format=json", help="HTTPS endpoint returning the observed IP")
    geo.add_argument("--json", action="store_true", dest="as_json", help="emit JSON only")
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
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")) if as_json else "\n".join(f"{key}: {value}" for key, value in payload.items()))


async def _sync(url: str, database: str) -> dict[str, object]:
    registry = SQLiteRegistry(database)
    try:
        result = await Syncer(registry).sync_url(url)
        return {"changed": result.changed, "invalid_entries": result.invalid_entries, "nodes": result.parsed_nodes, "not_modified": result.not_modified, "status": result.status, "used_last_valid": result.used_last_valid}
    finally:
        registry.close()


async def _geo(config_path: str, node_id: str, exit_ip_url: str) -> dict[str, object]:
    config = HoplineConfig.from_file(config_path)
    registry = SQLiteRegistry(config.database)
    try:
        if node_id not in {node.id for node in registry.list_nodes()}:
            raise ValueError(f"node not found: {node_id}")
        ip = await asyncio.to_thread(
            fetch_exit_ip,
            proxy_host=config.gateway_host,
            proxy_port=config.gateway_port,
            proxy_username=f"node-{node_id}",
            proxy_password=config.proxy_password,
            target_url=exit_ip_url,
        )
        result = await asyncio.to_thread(GeolocationResolver().resolve, ip)
        registry.save_geolocation(node_id, result)
        return {
            "node": node_id,
            "ip": result.ip,
            "country_code": result.country_code,
            "country": result.country,
            "asn": result.asn,
            "organization": result.organization,
            "provider": result.provider,
            "checked_at": result.checked_at,
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
    from .metrics import MetricsServer
    from .probe import ActiveProbeScheduler

    config = HoplineConfig.from_file(config_path)
    registry = SQLiteRegistry(config.database)
    health = HealthChecker(registry)
    engine = SingBoxEngine(
        binary=config.sing_box_binary,
        base_port=config.tunnel_port,
        workdir=config.engine_workdir,
    )
    gateway: Gateway | None = None
    scheduler: SubscriptionScheduler | None = None
    metrics = MetricsServer(
        registry,
        host=config.metrics_host,
        port=config.metrics_port,
        probe_enabled=bool(config.probe_targets),
    ) if config.metrics_enabled else None
    control = ControlServer(registry, port=config.control_port)
    probe_scheduler = None
    probe_task = None

    def publish_generation(generation: Generation) -> None:
        if gateway is None:
            return
        gateway.publish_generation(
            generation.port,
            {node.id: node.credential for node in registry.list_nodes()},
        )

    scheduler = SubscriptionScheduler(
        Syncer(registry),
        config.subscriptions,
        static_nodes=config.static_nodes,
        engine=engine,
        on_generation=publish_generation,
        interval=config.interval,
        jitter=config.jitter,
    )
    if metrics is not None:
        await metrics.start()
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
        results = await scheduler.sync_once()
        nodes = registry.list_nodes()
        if not results or not nodes or engine.manager.active is None:
            return 2
        gateway = Gateway(
            host=config.gateway_host,
            port=config.gateway_port,
            generation_port=engine.manager.active.port,
            generation_credentials={node.id: node.credential for node in nodes},
            health_state=lambda node_id: (record.state if (record := registry.health_record(node_id)) else None),
            health_available=health.is_available,
            record_success=lambda node_id: health.record_success(node_id),
            record_failure=lambda node_id, error: health.record_failure(node_id, error),
            max_active_connections=config.max_active_connections,
            proxy_username=config.proxy_username,
            proxy_password=config.proxy_password,
        )
        await gateway.start()
        if config.probe_targets:
            probe = None
            if config.probe_mode == "http":
                from functools import partial
                from .probe import http_connect_probe
                probe = partial(http_connect_probe, proxy_host=config.probe_proxy_host, proxy_port=config.probe_proxy_port)
            probe_scheduler = ActiveProbeScheduler(
                health,
                registry.list_nodes,
                config.probe_targets,
                interval=config.probe_interval,
                timeout=config.probe_timeout,
                **({"probe": probe} if probe is not None else {}),
            )
            probe_task = asyncio.create_task(probe_scheduler.run())
        if once:
            print(json.dumps({
                "sources": len(results),
                "nodes": len(nodes),
                "control_port": control.port,
                "gateway_port": gateway.port,
                "metrics_port": metrics.port if metrics else None,
                "tunnel_port": engine.manager.active.port,
                "once": True,
            }, sort_keys=True))
            return 0
        await scheduler.run(initial_sync=False)
        return 0
    finally:
        scheduler.stop()
        if probe_scheduler is not None:
            probe_scheduler.stop()
        if probe_task is not None:
            probe_task.cancel()
            await asyncio.gather(probe_task, return_exceptions=True)
        if gateway is not None:
            await gateway.stop()
            await gateway.wait_closed()
        await engine.close()
        if metrics is not None:
            await metrics.stop()
        await control.stop()
        registry.close()

def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "geo":
            payload = asyncio.run(_geo(args.config, args.node, args.exit_ip_url))
            _emit(payload, args.as_json)
            return 0
        if args.command == "doctor":
            payload = _doctor(args.db)
            _emit(payload, args.as_json)
            return 0 if payload["sing_box"] else 2
        if args.command in {"status", "nodes"}:
            _emit(asyncio.run(_control_request(args.host, args.port, "/" + args.command)), args.as_json)
            return 0
        payload = asyncio.run(_sync(_require_url(args.url), args.db))
        _emit(payload, args.as_json)
        return 0 if payload["nodes"] else 2
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"hopline: {error}", file=sys.stderr)
        return 2
