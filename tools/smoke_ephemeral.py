from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from hopline.gateway import Gateway
from hopline.models import Node
from hopline.parser import parse_share_link
from hopline.singbox import build_config
PROTOCOL_FILES = {
    "vless": "vless-node.txt",
    "vmess": "vmess-node.txt",
    "trojan": "trojan-node.txt",
    "shadowsocks": "shadowsocks-node.txt",
}


def free_port() -> int:
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def first_link(path: Path) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith("#"):
            return value
    raise ValueError(f"fixture contains no share link: {path.name}")


def wait_for_port(port: int, process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("sing-box exited before the ephemeral listener opened")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise TimeoutError("ephemeral sing-box listener did not open")


def clean_curl_environment() -> dict[str, str]:
    environment = os.environ.copy()
    for key in (
        "ALL_PROXY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "NO_PROXY",
        "all_proxy",
        "http_proxy",
        "https_proxy",
        "no_proxy",
    ):
        environment.pop(key, None)
    return environment


async def proxy_status(port: int, authorization: str | None) -> str:
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    try:
        request = b"CONNECT example.com:443 HTTP/1.1\r\nHost: example.com:443\r\n"
        if authorization is not None:
            request += b"Proxy-Authorization: Basic " + authorization.encode("ascii") + b"\r\n"
        writer.write(request + b"\r\n")
        await writer.drain()
        response = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3)
        return response.split(b" ", 2)[1].decode("ascii")
    finally:
        writer.close()
        await writer.wait_closed()


def curl_status(port: int, *, username: str, password: str, timeout: float) -> str:
    command = [
        "curl",
        "--silent",
        "--show-error",
        "--output",
        os.devnull,
        "--write-out",
        "%{http_code}",
        "--max-time",
        str(timeout),
        "--proxy",
        f"http://127.0.0.1:{port}",
        "--proxy-user",
        f"{username}:{password}",
        "https://api.ipify.org?format=json",
    ]
    result = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout + 3,
        env=clean_curl_environment(),
    )
    status = result.stdout.strip()
    if len(status) != 3 or not status.isdigit():
        raise RuntimeError(f"curl did not return an HTTP status ({result.returncode})")
    return status


def assert_dns_bootstrap(config: dict[str, Any], node: Node) -> None:
    dns = config["dns"]
    servers = {server["tag"]: server for server in dns["servers"]}
    remote = servers[f"dns-remote-{node.id}"]
    outbound = next(item for item in config["outbounds"] if item.get("tag") == node.id)
    if dns["final"] != "dns-direct":
        raise AssertionError("DNS final resolver is not dns-direct")
    if remote["detour"] != node.id:
        raise AssertionError("target DNS detour does not match the authenticated node")
    if remote.get("domain_resolver") != "dns-direct":
        raise AssertionError("remote DNS bootstrap does not use dns-direct")
    if outbound.get("domain_resolver") != "dns-direct":
        raise AssertionError("node hostname does not use dns-direct")
    relay_rule = next(
        rule for rule in dns["rules"] if rule.get("domain") == [node.server]
    )
    if relay_rule["server"] != "dns-direct":
        raise AssertionError("node hostname is not routed to dns-direct")
    user = config["inbounds"][0]["users"][0]
    if user["username"] != node.id or user["password"] != node.credential:
        raise AssertionError("ephemeral auth credential does not match the node")
    auth_route = next(
        rule for rule in config["route"]["rules"] if rule.get("auth_user") == [node.id]
    )
    if auth_route["outbound"] != node.id:
        raise AssertionError("auth_user does not select the node outbound")


async def gateway_smoke(port: int, tunnel_port: int, node: Node, timeout: float) -> dict[str, str]:
    gateway = Gateway(
        host="127.0.0.1",
        port=0,
        generation_port=tunnel_port,
        generation_credentials={node.id: node.credential},
        proxy_username="hopline",
        proxy_password="fixture-local-password",
    )
    await gateway.start()
    try:
        gateway_port = gateway.port
        if gateway_port is None:
            raise RuntimeError("ephemeral Hopline gateway did not open")
        authenticated = await asyncio.to_thread(
            curl_status, gateway_port, username="hopline", password="fixture-local-password", timeout=timeout
        )
        invalid = await proxy_status(
            gateway_port,
            base64.b64encode(b"hopline:wrong-password").decode("ascii"),
        )
        unauthenticated = await proxy_status(gateway_port, None)
        if not 200 <= int(authenticated) <= 399:
            raise RuntimeError(f"authenticated CONNECT did not reach the target (status {authenticated})")
        if invalid != "407" or unauthenticated != "407":
            raise RuntimeError("invalid or missing proxy credential did not return 407")
        return {"authenticated": authenticated, "invalid_credential": invalid, "missing_credential": unauthenticated}
    finally:
        await gateway.stop()
        await gateway.wait_closed()


def smoke_node(binary: str, node: Node, timeout: float) -> dict[str, str]:
    port = free_port()
    config = build_config([node], listen_port=port)
    assert_dns_bootstrap(config, node)
    with tempfile.TemporaryDirectory(prefix="hopline-ephemeral-smoke-") as directory:
        config_path = Path(directory) / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        check = subprocess.run(
            [binary, "check", "-c", str(config_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if check.returncode:
            raise RuntimeError("sing-box rejected the ephemeral generated config")
        process = subprocess.Popen(
            [binary, "run", "-c", str(config_path), "--disable-color"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            wait_for_port(port, process)
            return asyncio.run(gateway_smoke(port, port, node, timeout))
        finally:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run credential-safe ephemeral Hopline egress smoke tests."
    )
    parser.add_argument("--fixture-dir", type=Path, default=Path("."))
    parser.add_argument("--sing-box", default="sing-box")
    parser.add_argument("--timeout", type=float, default=20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if shutil.which(args.sing_box) is None and not Path(args.sing_box).is_file():
        print("sing-box binary not found", file=sys.stderr)
        return 2
    results: dict[str, dict[str, str]] = {}
    try:
        for protocol, filename in PROTOCOL_FILES.items():
            node = parse_share_link(first_link(args.fixture_dir / filename))
            expected_protocol = "ss" if protocol == "shadowsocks" else protocol
            if node.protocol != expected_protocol:
                raise ValueError(f"{filename} does not contain a {protocol} node")
            results[protocol] = smoke_node(args.sing_box, node, args.timeout)
    except (OSError, RuntimeError, TimeoutError, ValueError, AssertionError) as error:
        print(f"ephemeral smoke failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps({"production_service_touched": False, "results": results}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
