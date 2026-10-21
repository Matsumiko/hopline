"""Reproducible local benchmarks for Hopline gateway and generation lifecycle.

No subscription, node, or credential is required. Every scenario runs against
in-process fake upstreams so results are comparable across machines.

    PYTHONPATH=. python3 tools/benchmark.py --json
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import platform
import statistics
import time
from typing import Any

from hopline.gateway import Gateway
from hopline.generation import Generation, GenerationManager

TOKEN = base64.b64encode(b"hopline:x").decode()


async def _upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        await reader.readuntil(b"\r\n\r\n")
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()
        await writer.wait_closed()


async def bench_admission(concurrency: int, limit: int) -> dict[str, Any]:
    admitted = 0
    release = asyncio.Event()

    async def upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        nonlocal admitted
        try:
            await reader.readuntil(b"\r\n\r\n")
            admitted += 1
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            await release.wait()
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(upstream, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    gateway = Gateway(host="127.0.0.1", port=0, generation_port=port,
                      generation_credentials={"node-a": "x"},
                      max_active_connections=limit, proxy_password="x")
    await gateway.start()

    async def request() -> int:
        reader, writer = await asyncio.open_connection("127.0.0.1", gateway.port)
        writer.write(f"CONNECT origin.test:443 HTTP/1.1\r\nProxy-Authorization: Basic {TOKEN}\r\n\r\n".encode())
        await writer.drain()
        response = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 5)
        status = int(response.split(b" ", 2)[1])
        if status == 200:
            await asyncio.sleep(0.01)
        writer.close()
        await writer.wait_closed()
        return status

    started = time.perf_counter()
    statuses = await asyncio.gather(*(request() for _ in range(concurrency)))
    elapsed = (time.perf_counter() - started) * 1000
    release.set()
    await gateway.stop()
    await gateway.wait_closed()
    server.close()
    await server.wait_closed()
    return {
        "scenario": "admission",
        "concurrency": concurrency,
        "limit_per_node": limit,
        "admitted": admitted,
        "accepted": statuses.count(200),
        "rejected": statuses.count(503),
        "elapsed_ms": round(elapsed, 1),
    }


async def bench_relay_throughput(chunks: int, chunk_bytes: int) -> dict[str, Any]:
    server = await asyncio.start_server(_upstream, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    gateway = Gateway(host="127.0.0.1", port=0, generation_port=port,
                      generation_credentials={"node-a": "x"}, proxy_password="x")
    await gateway.start()

    reader, writer = await asyncio.open_connection("127.0.0.1", gateway.port)
    writer.write(f"CONNECT origin.test:443 HTTP/1.1\r\nProxy-Authorization: Basic {TOKEN}\r\n\r\n".encode())
    await writer.drain()
    await reader.readuntil(b"\r\n\r\n")

    payload = b"x" * chunk_bytes
    started = time.perf_counter()
    for _ in range(chunks):
        writer.write(payload)
        await writer.drain()
    received = 0
    while received < chunks * chunk_bytes:
        data = await reader.read(65536)
        if not data:
            break
        received += len(data)
    elapsed = time.perf_counter() - started

    writer.close()
    await writer.wait_closed()
    await gateway.stop()
    await gateway.wait_closed()
    server.close()
    await server.wait_closed()
    total = chunks * chunk_bytes
    return {
        "scenario": "relay_throughput",
        "bytes": total,
        "received_bytes": received,
        "elapsed_s": round(elapsed, 3),
        "throughput_mib_s": round((received / (1024 * 1024)) / elapsed, 1) if elapsed else None,
    }


async def bench_generation_swap(connections: int) -> dict[str, Any]:
    server = await asyncio.start_server(_upstream, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    manager = GenerationManager()
    old = Generation(label="old", port=port, credentials={"node-a": "x"})
    manager.promote(old)
    gateway = Gateway(host="127.0.0.1", port=0, generation_port=port,
                      generation_credentials={"node-a": "x"}, proxy_password="x")
    gateway.attach_generations(manager)
    await gateway.start()

    async def open_stream() -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        reader, writer = await asyncio.open_connection("127.0.0.1", gateway.port)
        writer.write(f"CONNECT origin.test:443 HTTP/1.1\r\nProxy-Authorization: Basic {TOKEN}\r\n\r\n".encode())
        await writer.drain()
        await reader.readuntil(b"\r\n\r\n")
        return reader, writer

    streams = [await open_stream() for _ in range(connections)]
    started = time.perf_counter()
    new = Generation(label="new", port=port, credentials={"node-a": "x"})
    manager.publish(new)
    gateway.publish_generation(new.port, new.credentials)
    swap_ms = (time.perf_counter() - started) * 1000

    alive = 0
    for reader, writer in streams:
        writer.write(b"ping")
        await writer.drain()
        try:
            if await asyncio.wait_for(reader.readexactly(4), 2) == b"ping":
                alive += 1
        except (asyncio.TimeoutError, asyncio.IncompleteReadError):
            pass
        writer.close()
        await writer.wait_closed()

    drain_started = time.perf_counter()
    await asyncio.wait_for(old.drained.wait(), 5)
    drain_ms = (time.perf_counter() - drain_started) * 1000

    await gateway.wait_closed()
    server.close()
    await server.wait_closed()
    return {
        "scenario": "generation_swap",
        "connections": connections,
        "streams_alive_after_swap": alive,
        "swap_publish_ms": round(swap_ms, 2),
        "drain_after_close_ms": round(drain_ms, 1),
    }


def _percentiles(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values)
    return {
        "min": round(ordered[0], 1),
        "p50": round(statistics.median(ordered), 1),
        "max": round(ordered[-1], 1),
    }


async def run_all(rounds: int) -> dict[str, Any]:
    admission = [await bench_admission(64, 8) for _ in range(rounds)]
    relay = [await bench_relay_throughput(64, 16384) for _ in range(rounds)]
    swap = [await bench_generation_swap(16) for _ in range(rounds)]
    return {
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "rounds": rounds,
        },
        "admission": {
            "raw": admission,
            "accepted": _percentiles([float(item["accepted"]) for item in admission]),
            "elapsed_ms": _percentiles([item["elapsed_ms"] for item in admission]),
        },
        "relay_throughput": {
            "raw": relay,
            "throughput_mib_s": _percentiles([item["throughput_mib_s"] for item in relay]),
        },
        "generation_swap": {
            "raw": swap,
            "swap_publish_ms": _percentiles([item["swap_publish_ms"] for item in swap]),
            "streams_alive": _percentiles([float(item["streams_alive_after_swap"]) for item in swap]),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run reproducible Hopline benchmarks.")
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.rounds < 1:
        parser.error("--rounds must be positive")
    report = asyncio.run(run_all(args.rounds))
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    env = report["environment"]
    print(f"python={env['python']} rounds={env['rounds']}")
    for name in ("admission", "relay_throughput", "generation_swap"):
        section = report[name]
        metrics = ", ".join(f"{key}={value}" for key, value in section.items() if key != "raw")
        print(f"{name}: {metrics}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
