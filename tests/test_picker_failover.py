import asyncio
import base64
import unittest

from hopline.gateway import Gateway
from hopline.health import HealthState
from hopline.picker import NodePicker


class PickerFailoverTests(unittest.TestCase):
    def test_picker_skips_dead_and_quarantine_nodes(self) -> None:
        states = {"a": HealthState.DEAD, "b": HealthState.HEALTHY, "c": HealthState.QUARANTINE}
        picker = NodePicker(states, state=states.get)
        self.assertEqual(picker.candidates("rotate"), ["b"])
        self.assertEqual(picker.candidates("a"), [])

    def test_gateway_fails_over_before_client_200(self) -> None:
        async def scenario() -> None:
            attempts: list[str] = []

            async def upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
                try:
                    request = await reader.readuntil(b"\r\n\r\n")
                    auth = request.split(b"Proxy-Authorization: Basic ", 1)[1].split(b"\r\n", 1)[0]
                    node_id = base64.b64decode(auth).decode().split(":", 1)[0]
                    attempts.append(node_id)
                    if node_id == "node-a":
                        writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                    else:
                        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                    await writer.drain()
                    if node_id == "node-b":
                        await asyncio.sleep(0.05)
                finally:
                    writer.close()
                    await writer.wait_closed()

            server = await asyncio.start_server(upstream, "127.0.0.1", 0)
            port = server.sockets[0].getsockname()[1]
            failures: list[tuple[str, str]] = []
            successes: list[str] = []
            gateway = Gateway(
                host="127.0.0.1",
                port=0,
                generation_port=port,
                generation_credentials={"node-a": "x", "node-b": "x"},
                record_success=successes.append,
                record_failure=lambda node, error: failures.append((node, error)),
            )
            await gateway.start()
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", gateway.port)
                token = base64.b64encode(b"rotate:x").decode()
                writer.write(f"CONNECT target.test:443 HTTP/1.1\r\nProxy-Authorization: Basic {token}\r\n\r\n".encode())
                await writer.drain()
                response = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
                self.assertEqual(response, b"HTTP/1.1 200 Connection Established\r\n\r\n")
                self.assertEqual(attempts, ["node-a", "node-b"])
                self.assertEqual(successes, ["node-b"])
                self.assertEqual(failures, [("node-a", "upstream_rejected")])
                writer.close()
                await writer.wait_closed()
            finally:
                await gateway.stop()
                await gateway.wait_closed()
                server.close()
                await server.wait_closed()

        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
