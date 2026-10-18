from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from .config import HoplineConfig
from .engine import SingBoxEngine
from .geolocation import DEFAULT_EXIT_IP_URL, GeolocationResolver, fetch_exit_ip, is_fresh
from .gateway import Gateway
from .generation import Generation
from .health import HealthChecker, HealthState
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
    geo = subparsers.add_parser("geo", help="Resolve the exit IP and country of one or more nodes")
    geo_target = geo.add_mutually_exclusive_group(required=True)
    geo_target.add_argument("--node", help="node ID to test")
    geo_target.add_argument("--all", action="store_true", help="resolve all nodes missing fresh country metadata")
    geo.add_argument("--concurrency", type=int, default=2, help="maximum concurrent node lookups with --all")
    geo.add_argument("--limit", type=int, help="maximum number of nodes to refresh with --all")
    geo.add_argument("--config", default=os.environ.get("HOPLINE_CONFIG", "hopline.toml"), help="TOML config path")
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


async def _resolve_geo_node(
    config: HoplineConfig,
    registry: SQLiteRegistry,
    node_id: str,
    exit_ip_url: str,
    resolver: GeolocationResolver,
) -> dict[str, object]:
    ip = await asyncio.to_thread(
        fetch_exit_ip,
        proxy_host=config.gateway_host,
        proxy_port=config.gateway_port,
        proxy_username=f"node-{node_id}",
        proxy_password=config.proxy_password,
        target_url=exit_ip_url,
    )
    result = await asyncio.to_thread(resolver.resolve, ip)
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


async def _geo(config_path: str, node_id: str, exit_ip_url: str) -> dict[str, object]:
    config = HoplineConfig.from_file(config_path)
    registry = SQLiteRegistry(config.database)
    try:
        if node_id not in {node.id for node in registry.list_nodes()}:
            raise ValueError(f"node not found: {node_id}")
        return await _resolve_geo_node(config, registry, node_id, exit_ip_url, GeolocationResolver())
    finally:
        registry.close()


async def _geo_all(
    config_path: str,
    exit_ip_url: str,
    concurrency: int,
    limit: int | None = None,
) -> dict[str, object]:
    if concurrency <= 0:
        raise ValueError("geo concurrency must be positive")
    if limit is not None and limit <= 0:
        raise ValueError("geo limit must be positive")
    config = HoplineConfig.from_file(config_path)
    registry = SQLiteRegistry(config.database)
    try:
        now = time.time()
        records = {row["node_id"]: row for row in registry.list_geolocation()}
        selected: list[str] = []
        skipped = {"fresh": 0, "dead": 0, "quarantine": 0}
        for node in registry.list_nodes():
            health = registry.health_record(node.id)
            if health is not None and health.state == HealthState.DEAD:
                skipped["dead"] += 1
                continue
            if health is not None and health.state == HealthState.QUARANTINE:
                skipped["quarantine"] += 1
                continue
            geo = records.get(node.id)
            if geo is not None and 0 <= now - geo["checked_at"] <= config.country_max_age:
                skipped["fresh"] += 1
                continue
            selected.append(node.id)
            if limit is not None and limit > 0 and len(selected) >= limit:
                break
        resolver = GeolocationResolver()
        semaphore = asyncio.Semaphore(concurrency)
        successes: list[dict[str, object]] = []
        errors: dict[str, int] = {}

        async def resolve(node_id: str) -> None:
            async with semaphore:
                try:
                    successes.append(await _resolve_geo_node(config, registry, node_id, exit_ip_url, resolver))
                except Exception as error:
                    name = type(error).__name__
                    errors[name] = errors.get(name, 0) + 1

        await asyncio.gather(*(resolve(node_id) for node_id in selected))
        countries: dict[str, int] = {}
        for result in successes:
            country = str(result["country_code"])
            countries[country] = countries.get(country, 0) + 1
        return {
            "mode": "all",
            "selected": len(selected),
            "updated": len(successes),
            "failed": len(selected) - len(successes),
            "errors": errors,
            "skipped": skipped,
            "countries": countries,
        }
    finally:
        registry.close()

async def _capability_all(config_path: str) -> dict[str, object]:
    config = HoplineConfig.from_file(config_path)
    registry = SQLiteRegistry(config.database)
    try:
        now = time.time()
        selected: list[tuple[str, str]] = []
        for node in registry.list_nodes():
            health = registry.health_record(node.id)
            if health is not None and health.state in {HealthState.DEAD, HealthState.QUARANTINE}:
                continue
            for family in ("ipv4", "ipv6"):
                record = registry.capability_record(node.id, family)
                if record is not None and record.ip is not None and record.is_fresh(now=now, max_age=config.capability_max_age):
                    continue
                selected.append((node.id, family))
        semaphore = asyncio.Semaphore(config.capability_concurrency)
        updated = 0
        errors: dict[str, int] = {}

        async def resolve(node_id: str, family: str) -> None:
            nonlocal updated
            async with semaphore:
                url = config.capability_ipv4_url if family == "ipv4" else config.capability_ipv6_url
                try:
                    ip = await asyncio.to_thread(
                        fetch_exit_ip,
                        proxy_host=config.gateway_host,
                        proxy_port=config.gateway_port,
                        proxy_username=f"node-{node_id}",
                        proxy_password=config.proxy_password,
                        target_url=url,
                        timeout=config.capability_timeout,
                        expected_family=family,
                    )
                    registry.save_capability(node_id, family, ip, time.time())
                    updated += 1
                except Exception as error:
                    registry.save_capability(node_id, family, None, time.time(), type(error).__name__)
                    name = type(error).__name__
                    errors[name] = errors.get(name, 0) + 1

        await asyncio.gather(*(resolve(node_id, family) for node_id, family in selected))
        return {"selected": len(selected), "updated": updated, "failed": len(selected) - updated, "errors": errors}
    finally:
        registry.close()


async def _capability_refresh_loop(config_path: str, interval: float) -> None:
    while True:
        try:
            await _capability_all(config_path)
        except (OSError, ValueError, RuntimeError):
            pass
        await asyncio.sleep(interval)


async def _geo_refresh_loop(
    config_path: str,
    interval: float,
    concurrency: int,
) -> None:
    while True:
        try:
            await _geo_all(config_path, DEFAULT_EXIT_IP_URL, concurrency)
        except (OSError, ValueError, RuntimeError):
            pass
        await asyncio.sleep(interval)

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
        reserved_ports=(config.gateway_port, config.control_port, config.metrics_port),
    )
    country_refresh_task = None
    capability_refresh_task = None
    gateway: Gateway | None = None
    scheduler: SubscriptionScheduler | None = None
    metrics = MetricsServer(
        registry,
        host=config.metrics_host,
        port=config.metrics_port,
        probe_enabled=bool(config.probe_targets),
    ) if config.metrics_enabled else None
    def accepted_credentials(nodes) -> dict[str, str]:
        accepted = set(engine.accepted_node_ids)
        return {
            node.id: node.credential
            for node in nodes
            if not accepted or node.id in accepted
        }

    def publish_generation(generation: Generation) -> None:
        if gateway is None:
            return
        gateway.publish_generation(
            generation.port,
            accepted_credentials(registry.list_nodes()),
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

    async def on_sync():
        results = await scheduler.sync_now()
        return [{"source": r.source, "changed": r.changed, "nodes": r.parsed_nodes} for r in results]

    async def probe_node_now(node) -> dict[str, object]:
        from .probe import ProbeTarget, http_connect_probe, tcp_target_probe

        if not config.probe_targets:
            raise RuntimeError("probe_not_configured")
        generation = engine.manager.active
        if generation is None:
            raise RuntimeError("no_active_generation")
        target = ProbeTarget(config.probe_targets[0])
        if config.probe_mode == "http":
            ok = await http_connect_probe(
                node, target,
                proxy_host=config.probe_proxy_host,
                proxy_port=generation.port,
            )
        else:
            ok = await tcp_target_probe(node, target)
        record = health.record_success(node.id) if ok else health.record_failure(node.id, "manual_probe_returned_false")
        return {"node_id": node.id, "action": "probe", "ok": ok, "state": record.state.value}

    async def handle_node_action(node_id: str, action: str) -> dict[str, object]:
        node = next((n for n in registry.list_nodes() if n.id == node_id), None)
        if node is None:
            raise ValueError("node_not_found")
        if action == "disable":
            record = health.quarantine(node_id)
            return {"node_id": node_id, "action": "disable", "state": record.state.value}
        if action == "enable":
            record = health.enable(node_id)
            return {"node_id": node_id, "action": "enable", "state": record.state.value if record else "unknown"}
        if action == "probe":
            return await probe_node_now(node)
        raise ValueError("unknown_action")

    control = ControlServer(
        registry,
        port=config.control_port,
        static_dir=config.webui_dir or None,
        sync_callback=on_sync,
        node_action_callback=handle_node_action,
    )
    probe_scheduler = None
    probe_task = None
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
            generation_credentials=accepted_credentials(nodes),
            health_state=lambda node_id: (record.state if (record := registry.health_record(node_id)) else None),
            health_available=health.is_available,
            country_metadata=lambda node_id: (
                (row["country_code"], row["checked_at"])
                if (row := registry.geolocation_record(node_id)) else None
            ),
            capability_metadata=lambda node_id, family: (
                (record.family, record.checked_at, record.ip)
                if (record := registry.capability_record(node_id, family)) and record.ip is not None
                else None
            ),
            country_max_age=config.country_max_age,
            capability_max_age=config.capability_max_age,
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
                from .probe import http_connect_probe

                async def probe(node, target):
                    generation = engine.manager.active
                    if generation is None:
                        return False
                    return await http_connect_probe(
                        node,
                        target,
                        proxy_host=config.probe_proxy_host,
                        proxy_port=generation.port,
                    )
            probe_scheduler = ActiveProbeScheduler(
                health,
                registry.list_nodes,
                config.probe_targets,
                interval=config.probe_interval,
                timeout=config.probe_timeout,
                concurrency=config.probe_concurrency,
                **({"probe": probe} if probe is not None else {}),
            )
            probe_task = asyncio.create_task(probe_scheduler.run())
        if not once:
            country_refresh_task = asyncio.create_task(
                _geo_refresh_loop(
                    config_path,
                    config.probe_interval,
                    config.probe_concurrency,
                )
            )
            if config.capability_enabled:
                capability_refresh_task = asyncio.create_task(
                    _capability_refresh_loop(config_path, config.capability_interval)
                )
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
        if country_refresh_task is not None:
            country_refresh_task.cancel()
            await asyncio.gather(country_refresh_task, return_exceptions=True)
        if capability_refresh_task is not None:
            capability_refresh_task.cancel()
            await asyncio.gather(capability_refresh_task, return_exceptions=True)
        await control.stop()
        if metrics is not None:
            await metrics.stop()
        registry.close()
def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "geo":
            if args.all:
                payload = asyncio.run(_geo_all(args.config, args.exit_ip_url, args.concurrency, args.limit))
            else:
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
        if args.command == "run":
            return asyncio.run(_run_daemon(args.config, args.once))
        payload = asyncio.run(_sync(_require_url(args.url), args.db))
        _emit(payload, args.as_json)
        return 0 if payload["nodes"] else 2
    except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as error:
        print(f"hopline: {error}", file=sys.stderr)
        return 2
