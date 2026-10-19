import tempfile
from pathlib import Path
import asyncio
import json
import unittest

from hopline.control import ControlServer
from hopline.health import HealthChecker, HealthState
from hopline.models import Node
from hopline.registry import SQLiteRegistry


class HealthControlTests(unittest.TestCase):
    def test_passive_failures_transition_to_dead(self) -> None:
        registry = SQLiteRegistry(":memory:")
        registry.replace_subscription("fixture", "hash", [Node("a", "vless", "a.test", 443, "uuid")])
        checker = HealthChecker(registry)
        checker.record_failure("a", "timeout")
        self.assertEqual(registry.health_record("a").state, HealthState.DEGRADED)
        checker.record_failure("a", "timeout")
        checker.record_failure("a", "timeout")
        self.assertEqual(registry.health_record("a").state, HealthState.DEAD)

    def test_active_probe_success_records_latency(self) -> None:
        registry = SQLiteRegistry(":memory:")
        registry.replace_subscription("fixture", "hash", [Node("a", "vless", "a.test", 443, "uuid")])
        checker = HealthChecker(registry, probe=lambda node: True)
        record = asyncio.run(checker.probe_node(registry.list_nodes()[0]))
        self.assertEqual(record.state, HealthState.HEALTHY)
        self.assertIsNotNone(record.latency_ms)

    def test_failure_cooldown_excludes_node_until_clock_advances(self) -> None:
        registry = SQLiteRegistry(":memory:")
        registry.replace_subscription("fixture", "hash", [Node("a", "vless", "a.test", 443, "uuid")])
        now = [100.0]
        checker = HealthChecker(registry, clock=lambda: now[0])

        record = checker.record_failure("a", "timeout")
        self.assertEqual(record.state, HealthState.DEGRADED)
        self.assertFalse(checker.is_available("a"))
        now[0] += 30.1
        self.assertTrue(checker.is_available("a"))

    def test_dead_node_uses_backoff_and_recovers_with_hysteresis(self) -> None:
        registry = SQLiteRegistry(":memory:")
        registry.replace_subscription("fixture", "hash", [Node("a", "vless", "a.test", 443, "uuid")])
        now = [100.0]
        checker = HealthChecker(registry, clock=lambda: now[0])

        checker.record_failure("a", "timeout")
        checker.record_failure("a", "timeout")
        record = checker.record_failure("a", "timeout")
        self.assertEqual(record.state, HealthState.DEAD)
        self.assertFalse(checker.should_probe("a"))
        now[0] += 60.1
        self.assertTrue(checker.should_probe("a"))
        self.assertEqual(checker.record_success("a").state, HealthState.DEGRADED)
        self.assertEqual(checker.record_success("a").state, HealthState.DEGRADED)
        self.assertEqual(checker.record_success("a").state, HealthState.HEALTHY)

    def test_status_breaks_down_totals_by_protocol_and_health(self) -> None:
        registry = SQLiteRegistry(":memory:")
        registry.replace_subscription(
            "fixture",
            "hash",
            [
                Node("vless-healthy", "vless", "vless.test", 443, "secret-1"),
                Node("vless-dead", "vless", "vless2.test", 443, "secret-2"),
                Node("vmess-healthy", "vmess", "vmess.test", 443, "secret-3"),
                Node("trojan-unknown", "trojan", "trojan.test", 443, "secret-4"),
            ],
        )
        registry.save_health("vless-healthy", HealthState.HEALTHY, 1, 0, 12.0, None)
        registry.save_health("vless-dead", HealthState.DEAD, 0, 3, None, "timeout")
        registry.save_health("vmess-healthy", HealthState.HEALTHY, 1, 0, 18.0, None)

        status = ControlServer(registry).status()

        self.assertEqual(status["nodes"], 4)
        self.assertEqual(status["health"]["healthy"], 2)
        self.assertEqual(status["health"]["dead"], 1)
        self.assertEqual(status["health"]["unknown"], 1)
        self.assertEqual(status["protocols"]["vless"], {
            "total": 2, "healthy": 1, "degraded": 0, "dead": 1, "quarantine": 0, "unknown": 0,
        })
        self.assertEqual(status["protocols"]["vmess"]["healthy"], 1)
        self.assertEqual(status["protocols"]["trojan"]["unknown"], 1)

    def test_status_breaks_down_country_and_unknown_metadata(self) -> None:
        registry = SQLiteRegistry(":memory:")
        registry.replace_subscription(
            "fixture",
            "hash",
            [
                Node("id-healthy", "vless", "id.test", 443, "secret-1"),
                Node("id-dead", "trojan", "id2.test", 443, "secret-2"),
                Node("no-country", "vmess", "unknown.test", 443, "secret-3"),
            ],
        )
        registry.save_health("id-healthy", HealthState.HEALTHY, 1, 0, 10.0, None)
        registry.save_health("id-dead", HealthState.DEAD, 0, 3, None, "timeout")
        from hopline.geolocation import GeoResult
        registry.save_geolocation(
            "id-healthy",
            GeoResult("203.0.113.10", "id", "Indonesia", "AS64500", "Example", "fixture", 10.0),
        )
        registry.save_geolocation(
            "id-dead",
            GeoResult("203.0.113.11", "ID", "Indonesia", "AS64500", "Example", "fixture", 10.0),
        )

        countries = ControlServer(registry).status()["countries"]

        self.assertEqual(countries["ID"], {
            "total": 2, "healthy": 1, "degraded": 0, "dead": 1, "quarantine": 0, "unknown": 0,
        })
        self.assertEqual(countries["unknown"], {
            "total": 1, "healthy": 0, "degraded": 0, "dead": 0, "quarantine": 0, "unknown": 1,
        })

    def test_control_api_exposes_geo_metadata_without_credentials(self) -> None:
        async def scenario() -> None:
            registry = SQLiteRegistry(":memory:")
            registry.replace_subscription("fixture", "hash", [Node("a", "vless", "a.test", 443, "secret-uuid")])
            from hopline.geolocation import GeoResult
            registry.save_geolocation("a", GeoResult("203.0.113.8", "ID", "Indonesia", "AS64500", "Example", "checkip", 10.0))
            server = ControlServer(registry, port=0)
            await server.start()
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
                writer.write(b"GET /nodes HTTP/1.1\r\nHost: localhost\r\n\r\n")
                await writer.drain()
                response = await reader.read()
                payload = json.loads(response.split(b"\r\n\r\n", 1)[1])
                self.assertEqual(payload["nodes"][0]["geolocation"]["country_code"], "ID")
                self.assertNotIn("secret-uuid", response.decode())
                writer.close()
                await writer.wait_closed()
            finally:
                await server.stop()

        asyncio.run(scenario())

    def test_control_api_returns_nodes_without_credentials(self) -> None:
        async def scenario() -> None:
            registry = SQLiteRegistry(":memory:")
            registry.replace_subscription("fixture", "hash", [Node("a", "vless", "a.test", 443, "secret-uuid")])
            server = ControlServer(registry, port=0)
            await server.start()
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
                writer.write(b"GET /nodes HTTP/1.1\r\nHost: localhost\r\n\r\n")
                await writer.drain()
                response = await reader.read()
                body = response.split(b"\r\n\r\n", 1)[1]
                payload = json.loads(body)
                self.assertEqual(payload["nodes"][0]["health"], "unknown")
                self.assertNotIn("secret-uuid", body.decode())
                writer.close()
                await writer.wait_closed()
            finally:
                await server.stop()

        asyncio.run(scenario())

    def test_control_api_serves_static_ui_and_blocks_path_traversal(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "dist"
                root.mkdir()
                (root / "index.html").write_text("<html>panel</html>", encoding="utf-8")
                (Path(directory) / "secret.txt").write_text("secret", encoding="utf-8")
                registry = SQLiteRegistry(":memory:")
                server = ControlServer(registry, port=0, static_dir=root)
                await server.start()
                try:
                    for path, expected in (("/", b"panel"), ("/../secret.txt", b"not_found")):
                        reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
                        writer.write(f"GET {path} HTTP/1.1\r\nHost: localhost\r\n\r\n".encode())
                        await writer.drain()
                        response = await reader.read()
                        if path == "/":
                            self.assertIn(b"HTTP/1.1 200 OK", response)
                            self.assertIn(expected, response)
                        else:
                            self.assertIn(b"HTTP/1.1 404 Not Found", response)
                            self.assertIn(expected, response)
                        writer.close()
                        await writer.wait_closed()
                finally:
                    await server.stop()
                    registry.close()

        asyncio.run(scenario())

    def test_control_api_handles_sync_with_and_without_callback(self) -> None:
        async def scenario() -> None:
            async def fake_sync():
                return [{"source": "fixture", "changed": True, "nodes": 3}]

            # With callback
            registry = SQLiteRegistry(":memory:")
            server = ControlServer(registry, port=0, sync_callback=fake_sync)
            await server.start()
            try:
                reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
                writer.write(b"POST /sync HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\n\r\n")
                await writer.drain()
                response = await reader.read()
                self.assertIn(b"200 OK", response)
                self.assertIn(b'"synced":1', response)
                writer.close()
                await writer.wait_closed()
            finally:
                await server.stop()
                registry.close()

            # Without callback
            registry2 = SQLiteRegistry(":memory:")
            server2 = ControlServer(registry2, port=0)
            await server2.start()
            try:
                reader2, writer2 = await asyncio.open_connection("127.0.0.1", server2.port)
                writer2.write(b"POST /sync HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\n\r\n")
                await writer2.drain()
                response2 = await reader2.read()
                self.assertIn(b"501 Not Implemented", response2)
                writer2.close()
                await writer2.wait_closed()
            finally:
                await server2.stop()
                registry2.close()

        asyncio.run(scenario())

    def test_control_api_dispatches_node_actions(self) -> None:
        async def scenario() -> None:
            registry = SQLiteRegistry(":memory:")
            registry.replace_subscription("fixture", "hash", [Node("node-a", "vless", "a.test", 443, "secret")])
            seen = []

            async def action(node_id, action_name):
                seen.append((node_id, action_name))
                return {"node_id": node_id, "action": action_name, "state": "quarantine"}

            server = ControlServer(registry, port=0, node_action_callback=action)
            await server.start()
            try:
                for name in ("disable", "enable", "probe"):
                    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
                    writer.write(f"POST /nodes/node-a/{name} HTTP/1.1\r\nHost: localhost\r\nContent-Length: 0\r\n\r\n".encode())
                    await writer.drain()
                    response = await reader.read()
                    self.assertIn(b"200 OK", response)
                    writer.close()
                    await writer.wait_closed()
                self.assertEqual(seen, [("node-a", "disable"), ("node-a", "enable"), ("node-a", "probe")])
            finally:
                await server.stop()
                registry.close()

        asyncio.run(scenario())

    def test_subscriptions_marks_managed_and_dispatches_add_delete(self) -> None:
        async def scenario() -> None:
            registry = SQLiteRegistry(":memory:")
            registry.replace_subscription("https://config.test/sub", "hash", [Node("a", "vless", "a.test", 443, "secret")])
            registry.add_managed_subscription("https://managed.test/sub")
            seen = []

            async def sub_callback(action, payload):
                seen.append((action, payload))
                return {"action": action, "ok": True}

            server = ControlServer(registry, port=0, subscription_callback=sub_callback)
            await server.start()
            try:
                listing = server.subscriptions()
                self.assertEqual(len(listing), 2)
                self.assertTrue(any(item["source"].startswith("managed.test#") for item in listing))

                for action, payload in (("add", b'{"url":"https://new.test/sub"}'), ("delete", b'{"digest":"aaaaaaaaaa"}')):
                    length = len(payload)
                    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
                    writer.write(
                        f"POST /subscriptions/{action} HTTP/1.1\r\nHost: localhost\r\n"
                        f"Content-Length: {length}\r\nContent-Type: application/json\r\n\r\n".encode() + payload
                    )
                    await writer.drain()
                    response = await reader.read()
                    self.assertIn(b"HTTP/1.1 200 OK", response)
                    writer.close()
                    await writer.wait_closed()
                self.assertEqual([item[0] for item in seen], ["add", "delete"])
                self.assertEqual(seen[0][1], {"url": "https://new.test/sub"})
                self.assertEqual(seen[1][1], {"digest": "aaaaaaaaaa"})
            finally:
                await server.stop()
                registry.close()

        asyncio.run(scenario())

    def test_control_api_auth_get_and_update(self) -> None:
        async def scenario() -> None:
            registry = SQLiteRegistry(":memory:")
            registry.set_setting("auth_username", "hopline")
            registry.set_setting("auth_password", "secret-pw")
            seen = []

            async def auth_callback(username, password):
                seen.append((username, password))
                return {"username": username, "password_set": True}

            server = ControlServer(registry, port=0, auth_callback=auth_callback)
            await server.start()
            try:
                # GET /auth returns username + password_set, never the password
                reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
                writer.write(b"GET /auth HTTP/1.1\r\nHost: localhost\r\n\r\n")
                await writer.drain()
                response = await reader.read()
                self.assertIn(b'"username":"hopline"', response)
                self.assertIn(b'"password_set":true', response)
                self.assertNotIn(b"secret-pw", response)
                writer.close(); await writer.wait_closed()

                # POST /auth dispatches and does not echo the password
                payload = b'{"username":"newuser","password":"newpass"}'
                reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
                writer.write(b"POST /auth HTTP/1.1\r\nHost: localhost\r\nContent-Type: application/json\r\nContent-Length: " + str(len(payload)).encode() + b"\r\n\r\n" + payload)
                await writer.drain()
                response = await reader.read()
                self.assertIn(b"200 OK", response)
                self.assertNotIn(b"newpass", response)
                writer.close(); await writer.wait_closed()
                self.assertEqual(seen, [("newuser", "newpass")])
            finally:
                await server.stop()
                registry.close()

        asyncio.run(scenario())

    def test_panel_login_flow_requires_session(self) -> None:
        async def scenario() -> None:
            from pathlib import Path
            import tempfile

            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory) / "dist"
                root.mkdir()
                (root / "index.html").write_text("<html>panel-app</html>", encoding="utf-8")
                registry = SQLiteRegistry(":memory:")
                registry.set_setting("auth_username", "hopline")
                registry.set_setting("auth_password", "secret-pw")
                registry.set_setting("panel_auth", "true")
                server = ControlServer(registry, port=0, static_dir=root)
                await server.start()

                async def raw_request(method: str, path: str, body: bytes = b"", *, cookie: str | None = None) -> tuple[bytes, str]:
                    reader, writer = await asyncio.open_connection("127.0.0.1", server.port)
                    headers = f"{method} {path} HTTP/1.1\r\nHost: localhost\r\n"
                    if cookie:
                        headers += f"Cookie: {cookie}\r\n"
                    if body:
                        headers += f"Content-Length: {len(body)}\r\nContent-Type: application/x-www-form-urlencoded\r\n"
                    writer.write(headers.encode() + b"\r\n" + body)
                    await writer.drain()
                    response = await reader.read()
                    writer.close()
                    await writer.wait_closed()
                    raw_head = response.split(b"\r\n\r\n", 1)[0]
                    return raw_head, response.decode("latin-1")

                try:
                    # No session → login page
                    head, body = await raw_request("GET", "/")
                    self.assertIn(b"HTTP/1.1 200 OK", head)
                    self.assertIn("<title>Hopline Login</title>", body)

                    # Wrong password → 401
                    head, _ = await raw_request("POST", "/panel/login", b"username=hopline&password=wrong")
                    self.assertIn(b"HTTP/1.1 401", head)

                    # Correct password → 302 + Set-Cookie
                    head, _ = await raw_request("POST", "/panel/login", b"username=hopline&password=secret-pw")
                    self.assertIn(b"HTTP/1.1 302", head)
                    self.assertIn(b"Set-Cookie: hopline_session=", head)
                    token = head.split(b"hopline_session=", 1)[1].split(b";", 1)[0].decode()

                    # With cookie → static panel
                    head, body = await raw_request("GET", "/", cookie=f"hopline_session={token}")
                    self.assertIn("panel-app", body)
                finally:
                    await server.stop()
                    registry.close()

        asyncio.run(scenario())

if __name__ == "__main__":
    unittest.main()
