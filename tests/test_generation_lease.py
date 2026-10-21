import asyncio
import unittest

from hopline.gateway import Gateway
from hopline.generation import Generation, GenerationManager


async def serve_proxy(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
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


class GenerationLeaseLifecycleTests(unittest.TestCase):
    def test_gateway_acquires_lease_and_blocks_drain_until_relay_ends(self) -> None:
        async def scenario() -> None:
            upstream = await asyncio.start_server(serve_proxy, "127.0.0.1", 0)
            upstream_port = upstream.sockets[0].getsockname()[1]
            manager = GenerationManager()
            old = Generation(label="old", port=upstream_port, credentials={"node-a": "x"})
            manager.promote(old)

            gateway = Gateway(
                host="127.0.0.1",
                port=0,
                generation_port=upstream_port,
                generation_credentials={"node-a": "x"},
                proxy_password="x",
            )
            gateway.attach_generations(manager)
            await gateway.start()

            reader, writer = await asyncio.open_connection("127.0.0.1", gateway.port)
            writer.write(
                b"CONNECT example.test:443 HTTP/1.1\r\n"
                b"Proxy-Authorization: Basic aG9wbGluZTp4\r\n\r\n"
            )
            await writer.drain()
            self.assertEqual(await reader.readuntil(b"\r\n\r\n"), b"HTTP/1.1 200 Connection Established\r\n\r\n")

            self.assertEqual(old.active_connections, 1, "gateway must hold a generation lease")

            # A new generation is published while the relay is still streaming.
            new = Generation(label="new", port=upstream_port, credentials={"node-a": "x"})
            manager.publish(new)
            self.assertFalse(old.accepting)
            self.assertFalse(
                old.drained.is_set(),
                "old generation must not be considered drained while a relay is active",
            )

            writer.write(b"still-alive")
            await asyncio.wait_for(writer.drain(), 2)
            self.assertEqual(await asyncio.wait_for(reader.readexactly(11), 2), b"still-alive")

            writer.close()
            await writer.wait_closed()
            await asyncio.wait_for(old.drained.wait(), 2)
            self.assertEqual(old.active_connections, 0)

            await gateway.wait_closed()
            upstream.close()
            await upstream.wait_closed()

        asyncio.run(scenario())

    def test_publish_keeps_counter_for_node_removed_from_new_generation(self) -> None:
        async def scenario() -> None:
            gateway = Gateway(
                host="127.0.0.1",
                port=0,
                generation_port=1,
                generation_credentials={"node-a": "x", "node-b": "y"},
                proxy_password="x",
            )
            self.assertTrue(gateway._reserve("node-a"))
            gateway.publish_generation(2, {"node-b": "y"})
            self.assertEqual(gateway._active_connections["node-a"], 1)
            gateway._release("node-a")
            self.assertEqual(gateway._active_connections["node-a"], 0)

        asyncio.run(scenario())

    def test_old_generation_is_not_stopped_before_its_connections_finish(self) -> None:
        async def scenario() -> None:
            manager = GenerationManager()
            old = Generation(label="old", port=1)
            manager.promote(old)
            lease = manager.acquire()
            new = Generation(label="new", port=2)
            manager.publish(new)

            drained = asyncio.Event()

            async def watch() -> None:
                await manager.wait_drained(old)
                drained.set()

            watcher = asyncio.create_task(watch())
            await asyncio.sleep(0.05)
            self.assertFalse(drained.is_set())

            await manager.release(lease)
            await asyncio.wait_for(drained.wait(), 2)
            watcher.cancel()
            await asyncio.gather(watcher, return_exceptions=True)

        asyncio.run(scenario())

    def test_lease_underflow_is_not_double_released(self) -> None:
        async def scenario() -> None:
            manager = GenerationManager()
            generation = Generation(label="gen", port=1)
            manager.promote(generation)
            lease = manager.acquire()
            await manager.release(lease)
            self.assertEqual(generation.active_connections, 0)
            # A second release must be a no-op, not an underflow crash.
            await manager.release(lease)
            self.assertEqual(generation.active_connections, 0)

        asyncio.run(scenario())

    def test_gateway_skips_node_missing_from_leased_generation(self) -> None:
        async def scenario() -> None:
            manager = GenerationManager()
            generation = Generation(label="gen", port=1, credentials={"node-b": "y"})
            manager.promote(generation)
            gateway = Gateway(
                host="127.0.0.1",
                port=0,
                generation_port=1,
                generation_credentials={"node-a": "x"},
                proxy_password="x",
            )
            gateway.attach_generations(manager)
            with self.assertRaises(RuntimeError):
                gateway._acquire_generation("node-a")
            self.assertEqual(
                generation.active_connections,
                0,
                "a rejected lease must not leave the generation counter incremented",
            )

        asyncio.run(scenario())

    def test_failed_new_generation_leaves_previous_active(self) -> None:
        async def scenario() -> None:
            manager = GenerationManager()
            old = Generation(label="old", port=1, credentials={"node-a": "x"})
            manager.promote(old)

            class FailingEngine:
                def __init__(self) -> None:
                    self.manager = manager

                async def start_generation(self, config):
                    raise RuntimeError("sing-box config rejected")

            engine = FailingEngine()
            try:
                await engine.start_generation({})
            except RuntimeError:
                pass
            self.assertIs(manager.active, old)
            self.assertTrue(old.accepting)
            self.assertTrue(old.drained.is_set())

        asyncio.run(scenario())

    def test_startup_attach_matches_published_generation(self) -> None:
        async def scenario() -> None:
            manager = GenerationManager()
            generation = Generation(label="gen-0", port=1, credentials={"node-a": "x"})
            manager.promote(generation)
            gateway = Gateway(
                host="127.0.0.1",
                port=0,
                generation_port=generation.port,
                generation_credentials={"node-a": "x"},
                proxy_password="x",
            )
            gateway.attach_generations(manager)
            port, credential = gateway._acquire_generation("node-a")[1:]
            self.assertEqual(port, generation.port)
            self.assertEqual(credential, "x")

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
