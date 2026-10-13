#!/usr/bin/env python3
"""Prove generation ownership without closing an active stream."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field


@dataclass
class Generation:
    label: str
    active: int = 0
    accepting: bool = True
    drained: asyncio.Event = field(default_factory=asyncio.Event)

    def __post_init__(self) -> None:
        self.drained.set()

    async def open(self) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        if not self.accepting:
            raise RuntimeError(f"generation {self.label} is draining")
        reader, writer = await asyncio.open_connection("127.0.0.1", 0)
        return reader, writer

    def acquire(self) -> None:
        self.active += 1
        self.drained.clear()

    def release(self) -> None:
        self.active -= 1
        if self.active == 0:
            self.drained.set()


class GenerationRouter:
    def __init__(self, generation: Generation) -> None:
        self.active = generation
        self.old: list[Generation] = []

    def publish(self, generation: Generation) -> None:
        previous = self.active
        self.active = generation
        previous.accepting = False
        self.old.append(previous)

    async def drain(self) -> None:
        await asyncio.gather(*(generation.drained.wait() for generation in self.old))


async def stream_server(
    generation: Generation,
) -> tuple[asyncio.AbstractServer, int]:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        generation.acquire()
        try:
            writer.write(f"generation={generation.label}\n".encode())
            await writer.drain()
            while data := await reader.readline():
                if data == b"close\n":
                    break
                writer.write(f"{generation.label}:{data.decode()}".encode())
                await writer.drain()
        finally:
            generation.release()
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, port

async def connect(port: int) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    return await asyncio.wait_for(asyncio.open_connection("127.0.0.1", port), 2)


async def main() -> None:
    first = Generation("old")
    second = Generation("new")
    router = GenerationRouter(first)
    old_server, old_port = await stream_server(first)
    new_server, new_port = await stream_server(second)
    try:
        old_reader, old_writer = await connect(old_port)
        if await asyncio.wait_for(old_reader.readline(), 2) != b"generation=old\n":
            raise AssertionError("old connection was not owned by old generation")

        router.publish(second)
        new_reader, new_writer = await connect(new_port)
        if await asyncio.wait_for(new_reader.readline(), 2) != b"generation=new\n":
            raise AssertionError("new connection was not owned by new generation")

        old_writer.write(b"still-alive\n")
        await asyncio.wait_for(old_writer.drain(), 2)
        if await asyncio.wait_for(old_reader.readline(), 2) != b"old:still-alive\n":
            raise AssertionError("old stream was interrupted by generation publish")

        old_writer.write(b"close\n")
        await asyncio.wait_for(old_writer.drain(), 2)
        old_writer.close()
        await asyncio.wait_for(old_writer.wait_closed(), 2)
        await asyncio.wait_for(router.drain(), 2)
        if first.active != 0 or first.accepting:
            raise AssertionError("old generation did not drain")

        new_writer.write(b"new-stream\n")
        await asyncio.wait_for(new_writer.drain(), 2)
        if await asyncio.wait_for(new_reader.readline(), 2) != b"new:new-stream\n":
            raise AssertionError("new stream did not remain on new generation")
        new_writer.write(b"close\n")
        await asyncio.wait_for(new_writer.drain(), 2)
        new_writer.close()
        await asyncio.wait_for(new_writer.wait_closed(), 2)

        print(
            "generation_swap=passed "
            "active_stream_preserved=passed "
            "new_connections_use_new_generation=passed"
        )
    finally:
        old_server.close()
        new_server.close()
        await old_server.wait_closed()
        await new_server.wait_closed()


if __name__ == "__main__":
    asyncio.run(main())
