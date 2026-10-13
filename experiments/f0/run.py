#!/usr/bin/env python3
"""Local sing-box F0 experiment: route authenticated users to two HTTP proxies."""

from __future__ import annotations

import asyncio
import base64
import json
import signal
import socket
import subprocess
import tempfile
from pathlib import Path

SING_BOX = "sing-box"
INBOUND_PORT = 18771
TARGET_PORT = 19090
PROXY_A_PORT = 19081
PROXY_B_PORT = 19082


async def read_headers(reader: asyncio.StreamReader) -> list[str]:
    lines: list[str] = []
    while True:
        raw = await reader.readline()
        if not raw:
            break
        line = raw.decode("latin-1").rstrip("\r\n")
        lines.append(line)
        if not line:
            break
    return lines


async def relay(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    except (ConnectionError, asyncio.IncompleteReadError):
        pass
    finally:
        writer.close()
        await writer.wait_closed()


async def handle_target(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    await read_headers(reader)
    writer.write(
        b"HTTP/1.1 200 OK\r\nContent-Length: 12\r\n"
        b"Connection: close\r\n\r\nF0-origin-ok"
    )
    await writer.drain()
    writer.close()
    await writer.wait_closed()


async def make_proxy(label: str, seen: list[str]) -> asyncio.AbstractServer:
    async def handle(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        lines = await read_headers(reader)
        if not lines or not lines[0].startswith("CONNECT "):
            writer.close()
            await writer.wait_closed()
            return
        seen.append(label)
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        try:
            target_reader, target_writer = await asyncio.open_connection(
                "127.0.0.1", TARGET_PORT
            )
        except OSError:
            writer.close()
            await writer.wait_closed()
            return
        await asyncio.gather(
            relay(reader, target_writer), relay(target_reader, writer)
        )

    return await asyncio.start_server(handle, "127.0.0.1", PROXY_A_PORT if label == "proxy-a" else PROXY_B_PORT)


def config(user_a_outbound: str = "proxy-a", user_b_outbound: str = "proxy-b") -> dict[str, object]:
    return {
        "log": {"level": "info"},
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": INBOUND_PORT,
                "users": [
                    {"username": "user-a", "password": "pass-a"},
                    {"username": "user-b", "password": "pass-b"},
                ],
            }
        ],
        "outbounds": [
            {
                "type": "http",
                "tag": "proxy-a",
                "server": "127.0.0.1",
                "server_port": PROXY_A_PORT,
            },
            {
                "type": "http",
                "tag": "proxy-b",
                "server": "127.0.0.1",
                "server_port": PROXY_B_PORT,
            },
            {"type": "direct", "tag": "direct"},
        ],
        "route": {
            "rules": [
                {
                    "inbound": ["mixed-in"],
                    "auth_user": ["user-a"],
                    "outbound": user_a_outbound,
                },
                {
                    "inbound": ["mixed-in"],
                    "auth_user": ["user-b"],
                    "outbound": user_b_outbound,
                },
            ],
            "final": "direct",
        },
    }


async def wait_for_port(port: int, process: subprocess.Popen[str] | None = None) -> None:
    for _ in range(100):
        if process is not None and process.poll() is not None:
            raise RuntimeError(f"sing-box exited early with code {process.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                return
        except OSError:
            await asyncio.sleep(0.05)
    raise TimeoutError(f"port {port} did not open")


async def open_tunnel(user: str, password: str) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    reader, writer = await asyncio.wait_for(
        asyncio.open_connection("127.0.0.1", INBOUND_PORT), 2
    )
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    writer.write(
        f"CONNECT 127.0.0.1:{TARGET_PORT} HTTP/1.1\r\n"
        f"Host: 127.0.0.1:{TARGET_PORT}\r\n"
        f"Proxy-Authorization: Basic {token}\r\n\r\n".encode()
    )
    await writer.drain()
    response = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
    if not response.startswith(b"HTTP/1.1 200"):
        writer.close()
        await writer.wait_closed()
        raise RuntimeError(f"CONNECT failed: {response!r}")
    return reader, writer


async def request(user: str, password: str) -> None:
    reader, writer = await open_tunnel(user, password)
    writer.write(b"GET / HTTP/1.1\r\nHost: f0.local\r\nConnection: close\r\n\r\n")
    await writer.drain()
    body = await asyncio.wait_for(reader.read(), 2)
    writer.close()
    try:
        await writer.wait_closed()
    except ConnectionError:
        pass
    if b"F0-origin-ok" not in body:
        raise RuntimeError(f"unexpected origin response: {body!r}")

async def request_until_routed(
    user: str, password: str, seen: list[str], expected: str
) -> None:
    for _ in range(100):
        before = len(seen)
        try:
            await request(user, password)
        except (ConnectionError, asyncio.IncompleteReadError, TimeoutError):
            await asyncio.sleep(0.05)
            continue
        if seen[before:] == [expected]:
            return
        await asyncio.sleep(0.05)
    raise TimeoutError(f"route {expected} was not observed after reload: {seen!r}")



async def main() -> None:
    seen: list[str] = []
    target = await asyncio.start_server(handle_target, "127.0.0.1", TARGET_PORT)
    proxy_a = await make_proxy("proxy-a", seen)
    proxy_b = await make_proxy("proxy-b", seen)
    process: subprocess.Popen[str] | None = None
    try:
        with tempfile.TemporaryDirectory(prefix="hopline-f0-") as directory:
            config_path = Path(directory) / "config.json"
            log_path = Path(directory) / "sing-box.log"
            config_path.write_text(json.dumps(config(), indent=2))
            check = subprocess.run(
                [SING_BOX, "check", "-c", str(config_path)],
                capture_output=True,
                text=True,
                check=False,
            )
            if check.returncode != 0:
                raise RuntimeError(f"config check failed: {check.stderr.strip()}")
            with log_path.open("w+") as log:
                process = subprocess.Popen(
                    [SING_BOX, "run", "-c", str(config_path), "--disable-color"],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                await wait_for_port(INBOUND_PORT, process)
                await request("user-a", "pass-a")
                await request("user-b", "pass-b")
                if seen != ["proxy-a", "proxy-b"]:
                    raise RuntimeError(f"unexpected proxy routing: {seen!r}")

                active_reader, active_writer = await open_tunnel("user-a", "pass-a")
                config_path.write_text(json.dumps(config("proxy-b", "proxy-a"), indent=2))
                process.send_signal(signal.SIGHUP)
                await wait_for_port(INBOUND_PORT, process)
                reload_survived = process.poll() is None
                before_reload_count = len(seen)
                await request_until_routed("user-a", "pass-a", seen, "proxy-b")
                routing_after_reload = seen[before_reload_count:]
                if not routing_after_reload or routing_after_reload[-1] != "proxy-b":
                    log.flush()
                    log.seek(0)
                    raise RuntimeError(
                        f"reload did not change user-a route: {seen!r}; "
                        f"process={process.poll()}; log={log.read()!r}"
                    )

                try:
                    active_writer.write(b"GET / HTTP/1.1\r\nHost: f0.local\r\nConnection: close\r\n\r\n")
                    await active_writer.drain()
                    active_body = await active_reader.read()
                    active_stream_survived = b"F0-origin-ok" in active_body
                except (ConnectionError, asyncio.IncompleteReadError):
                    active_stream_survived = False
                try:
                    await active_writer.wait_closed()
                except ConnectionError:
                    pass
                log.flush()
                log.seek(0)
                log_text = log.read()
                secrets_redacted = not any(secret in log_text for secret in ("pass-a", "pass-b"))
                if not secrets_redacted:
                    raise RuntimeError("credential appeared in sing-box output")
                if not reload_survived:
                    raise RuntimeError("SIGHUP terminated sing-box")
                print(json.dumps({
                    "sing_box": subprocess.check_output([SING_BOX, "version"], text=True).splitlines()[0],
                    "config_check": "passed",
                    "connect": "passed",
                    "routing_before_reload": seen[:2],
                    "routing_after_reload_attempts": routing_after_reload,
                    "routing_after_reload_final": routing_after_reload[-1],
                    "sighup_process_survived": reload_survived,
                    "active_stream_survived_reload": active_stream_survived,
                    "active_stream_closed_on_reload": not active_stream_survived,
                    "log_secret_scan": "passed",
                }, sort_keys=True))
    finally:
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        proxy_a.close()
        proxy_b.close()
        target.close()
        await proxy_a.wait_closed()
        await proxy_b.wait_closed()
        await target.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
