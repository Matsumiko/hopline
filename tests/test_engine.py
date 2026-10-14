import asyncio
import shutil
import unittest

from hopline.engine import SingBoxEngine


class SingBoxEngineTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("sing-box"), "sing-box is required")
    def test_engine_starts_and_stops_generation(self) -> None:
        async def scenario() -> None:
            engine = SingBoxEngine(base_port=18971)
            config = {
                "log": {"disabled": True},
                "inbounds": [
                    {
                        "type": "mixed",
                        "tag": "mixed-in",
                        "listen": "127.0.0.1",
                        "listen_port": 18971,
                        "users": [{"username": "node-a", "password": "fixture-secret"}],
                    }
                ],
                "outbounds": [{"type": "direct", "tag": "node-a"}],
                "route": {
                    "rules": [
                        {
                            "inbound": ["mixed-in"],
                            "auth_user": ["node-a"],
                            "outbound": "node-a",
                        }
                    ],
                    "final": "node-a",
                },
            }
            try:
                generation = await engine.start_generation(config)
                self.assertEqual(generation.port, 18971)
                self.assertIs(engine.manager.active, generation)
                self.assertIn(generation.label, engine._running)
                await engine.stop_generation(generation)
                self.assertNotIn(generation.label, engine._running)
            finally:
                await engine.close()

        asyncio.run(scenario())

    @unittest.skipUnless(shutil.which("sing-box"), "sing-box is required")
    def test_apply_nodes_reuses_generation_for_same_parameters(self) -> None:
        async def scenario() -> None:
            from hopline.models import Node

            engine = SingBoxEngine(base_port=18973)
            node = Node(
                id="node-a",
                protocol="vless",
                server="127.0.0.1",
                port=443,
                uuid="00000000-0000-4000-8000-000000000001",
            )
            try:
                first = await engine.apply_nodes([node])
                second = await engine.apply_nodes([node])
                self.assertIs(first, second)
                self.assertIs(engine.manager.active, first)
            finally:
                await engine.close()

        asyncio.run(scenario())

    @unittest.skipUnless(shutil.which("sing-box"), "sing-box is required")
    def test_gateway_reaches_local_target_through_generation(self) -> None:
        async def scenario() -> None:
            async def target(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                try:
                    await reader.readuntil(b"\r\n\r\n")
                    writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 9\r\n\r\nF1-target")
                    await writer.drain()
                finally:
                    writer.close()
                    await writer.wait_closed()

            target_server = await asyncio.start_server(target, "127.0.0.1", 0)
            target_port = target_server.sockets[0].getsockname()[1]
            engine = SingBoxEngine(base_port=18972)
            config = {
                "log": {"disabled": True},
                "inbounds": [{"type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1", "listen_port": 18972, "users": [{"username": "node-a", "password": "fixture-secret"}]}],
                "outbounds": [{"type": "direct", "tag": "node-a"}],
                "route": {"rules": [{"inbound": ["mixed-in"], "auth_user": ["node-a"], "outbound": "node-a"}], "final": "node-a"},
            }
            try:
                generation = await engine.start_generation(config)
                from hopline.gateway import Gateway

                gateway = Gateway(
                    host="127.0.0.1",
                    port=0,
                    generation_port=generation.port,
                    generation_credentials={"node-a": "fixture-secret"},
                    proxy_password="x",
                )
                await gateway.start()
                try:
                    reader, writer = await asyncio.open_connection("127.0.0.1", gateway.port)
                    writer.write(f"CONNECT 127.0.0.1:{target_port} HTTP/1.1\r\nProxy-Authorization: Basic aG9wbGluZTp4\r\n\r\n".encode())
                    await writer.drain()
                    self.assertTrue((await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 3)).startswith(b"HTTP/1.1 200"))
                    writer.write(f"GET / HTTP/1.1\r\nHost: local\r\n\r\n".encode())
                    await writer.drain()
                    self.assertIn(b"F1-target", await asyncio.wait_for(reader.read(), 3))
                    writer.close()
                    await writer.wait_closed()
                finally:
                    await gateway.stop()
                    await gateway.wait_closed()
            finally:
                await engine.close()
                target_server.close()
                await target_server.wait_closed()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
