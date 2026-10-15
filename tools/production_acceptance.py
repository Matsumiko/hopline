from __future__ import annotations

import argparse
import base64
import json
import socket
import ssl
import time
from dataclasses import dataclass
from ipaddress import ip_address
from urllib.parse import urlsplit

from hopline.config import HoplineConfig
from hopline.models import Node
from hopline.registry import SQLiteRegistry


PROTOCOL_NAMES = {"ss": "shadowsocks", "trojan": "trojan", "vless": "vless", "vmess": "vmess"}
DEFAULT_TARGET = "https://api.ipify.org?format=json"


class AcceptanceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AcceptanceResult:
    protocol: str
    node_id: str
    status: int | None
    exit_ip: str | None
    latency_ms: float | None
    success: bool
    error: str | None = None


def select_healthy_samples(
    nodes: list[Node], health_by_id: dict[str, Any], per_protocol: int,
) -> dict[str, list[Node]]:
    if per_protocol < 1:
        raise ValueError("per_protocol must be positive")
    selected: dict[str, list[Node]] = {name: [] for name in PROTOCOL_NAMES.values()}
    for node in sorted(nodes, key=lambda item: item.id):
        record = health_by_id.get(node.id)
        state = getattr(getattr(record, "state", None), "value", getattr(record, "state", None))
        if state != "healthy":
            continue
        protocol = PROTOCOL_NAMES.get(node.protocol)
        if protocol is not None and len(selected[protocol]) < per_protocol:
            selected[protocol].append(node)
    return selected


def public_result(result: AcceptanceResult) -> dict[str, object]:
    """Return only acceptance fields; never expose node connection parameters."""
    return {
        "protocol": result.protocol,
        "node_id": result.node_id,
        "status": result.status,
        "exit_ip": result.exit_ip,
        "latency_ms": result.latency_ms,
        "success": result.success,
        "error": result.error,
    }


def _target_parts(target: str) -> tuple[str, int, str]:
    parsed = urlsplit(target)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("target must be an HTTPS URL without credentials or fragment")
    port = parsed.port or 443
    path = parsed.path or "/"
    if parsed.query:
        path += "?" + parsed.query
    return parsed.hostname, port, path


def _read_headers(connection: socket.socket, limit: int = 64 * 1024) -> tuple[int, dict[str, str], bytes]:
    data = bytearray()
    while b"\r\n\r\n" not in data:
        chunk = connection.recv(4096)
        if not chunk:
            raise AcceptanceError("incomplete_http_headers")
        data.extend(chunk)
        if len(data) > limit:
            raise AcceptanceError("http_headers_too_large")
    raw, remainder = bytes(data).split(b"\r\n\r\n", 1)
    lines = raw.decode("latin-1").split("\r\n")
    try:
        status = int(lines[0].split(" ", 2)[1])
    except (IndexError, ValueError) as error:
        raise AcceptanceError("malformed_http_status") from error
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.lower()] = value.strip()
    return status, headers, remainder


def _read_body(connection: socket.socket, headers: dict[str, str], initial: bytes) -> bytes:
    length = headers.get("content-length")
    if length is not None:
        try:
            expected = int(length)
        except ValueError as error:
            raise AcceptanceError("malformed_content_length") from error
        if expected > 64 * 1024:
            raise AcceptanceError("response_body_too_large")
        body = bytearray(initial)
        while len(body) < expected:
            chunk = connection.recv(min(4096, expected - len(body)))
            if not chunk:
                raise AcceptanceError("incomplete_http_body")
            body.extend(chunk)
        return bytes(body[:expected])
    body = bytearray(initial)
    while len(body) <= 64 * 1024:
        chunk = connection.recv(4096)
        if not chunk:
            return bytes(body)
        body.extend(chunk)
    raise AcceptanceError("response_body_too_large")


def fetch_exit_ip(
    *, node_id: str, password: str, gateway_host: str, gateway_port: int,
    target: str, timeout: float,
) -> tuple[int, str, float]:
    target_host, target_port, target_path = _target_parts(target)
    started = time.perf_counter()
    connection = socket.create_connection((gateway_host, gateway_port), timeout=timeout)
    try:
        connection.settimeout(timeout)
        token = base64.b64encode(f"{node_id}:{password}".encode()).decode("ascii")
        connection.sendall(
            f"CONNECT {target_host}:{target_port} HTTP/1.1\r\n"
            f"Host: {target_host}:{target_port}\r\n"
            f"Proxy-Authorization: Basic {token}\r\n"
            "Connection: close\r\n\r\n".encode()
        )
        status, _headers, _remainder = _read_headers(connection)
        if status != 200:
            raise AcceptanceError(f"gateway_http_{status}")
        secure = ssl.create_default_context().wrap_socket(connection, server_hostname=target_host)
        connection = secure
        secure.sendall(
            f"GET {target_path} HTTP/1.1\r\nHost: {target_host}\r\n"
            "Accept: application/json\r\nConnection: close\r\n\r\n".encode()
        )
        status, headers, remainder = _read_headers(secure)
        body = _read_body(secure, headers, remainder)
        if status != 200:
            raise AcceptanceError(f"target_http_{status}")
        try:
            payload = json.loads(body.decode("utf-8"))
            value = payload["ip"] if isinstance(payload, dict) else payload
            address = str(ip_address(str(value)))
        except (UnicodeDecodeError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
            raise AcceptanceError("target_did_not_return_ip") from error
        return status, address, round((time.perf_counter() - started) * 1000, 1)
    finally:
        connection.close()


def _run_node(node: Node, config: HoplineConfig, target: str, timeout: float) -> AcceptanceResult:
    protocol = PROTOCOL_NAMES[node.protocol]
    try:
        status, exit_ip, latency_ms = fetch_exit_ip(
            node_id=node.id,
            password=config.proxy_password,
            gateway_host=config.gateway_host,
            gateway_port=config.gateway_port,
            target=target,
            timeout=timeout,
        )
    except (AcceptanceError, OSError, ssl.SSLError, TimeoutError, ValueError):
        return AcceptanceResult(protocol, node.id, None, None, None, False, "request_failed")
    return AcceptanceResult(protocol, node.id, status, exit_ip, latency_ms, True)


def run_acceptance(config_path: str, per_protocol: int, target: str, timeout: float) -> dict[str, object]:
    config = HoplineConfig.from_file(config_path)
    if config.gateway_host not in {"127.0.0.1", "::1", "localhost"} or config.gateway_port != 18770:
        raise ValueError("production acceptance requires the local gateway on port 18770")
    registry = SQLiteRegistry(config.database)
    try:
        nodes = registry.list_nodes()
        health = {record.node_id: record for record in registry.list_health()}
        samples = select_healthy_samples(nodes, health, per_protocol)
        results: list[AcceptanceResult] = []
        for protocol in PROTOCOL_NAMES.values():
            results.extend(_run_node(node, config, target, timeout) for node in samples[protocol])
        grouped: dict[str, list[dict[str, object]]] = {protocol: [] for protocol in PROTOCOL_NAMES.values()}
        for result in results:
            grouped[result.protocol].append(public_result(result))
        missing = [protocol for protocol, selected in samples.items() if len(selected) < per_protocol]
        failures = [result for result in results if not result.success]
        return {
            "production_pc_only": True,
            "requested_per_protocol": per_protocol,
            "selected_per_protocol": {protocol: len(nodes) for protocol, nodes in samples.items()},
            "missing_protocol_samples": missing,
            "results": grouped,
            "passed": not missing and not failures,
        }
    finally:
        registry.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run redacted forced-route acceptance on local production PC.")
    parser.add_argument("--config", default="/etc/hopline/hopline.toml")
    parser.add_argument("--per-protocol", type=int, default=3)
    parser.add_argument("--target", default=DEFAULT_TARGET)
    parser.add_argument("--timeout", type=float, default=15.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = run_acceptance(args.config, args.per_protocol, args.target, args.timeout)
    except (OSError, ValueError, RuntimeError) as error:
        print(f"production acceptance failed: {type(error).__name__}", file=__import__("sys").stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
