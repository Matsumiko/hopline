from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from .failures import parse_legacy
from .health import HealthState


class ControlServer:
    def __init__(
        self,
        registry: SQLiteRegistry,
        *,
        host: str = "127.0.0.1",
        port: int = 18772,
        static_dir: str | Path | None = None,
        sync_callback: Callable[[], Awaitable[list[dict[str, Any]]]] | None = None,
        node_action_callback: Callable[[str, str], Awaitable[dict[str, Any]]] | None = None,
        runtime_callback: Callable[[], Awaitable[dict[str, Any]]] | None = None,
        subscription_callback: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
        auth_callback: Callable[[str, str], Awaitable[dict[str, Any]]] | None = None,
    ) -> None:
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("control API must bind to localhost")
        self.registry = registry
        self.host = host
        self.requested_port = port
        self.static_dir = Path(static_dir).resolve() if static_dir else None
        self._sync_callback = sync_callback
        self._node_action_callback = node_action_callback
        self._runtime_callback = runtime_callback
        self._subscription_callback = subscription_callback
        self._auth_callback = auth_callback
        self.server: asyncio.AbstractServer | None = None
        self._sessions: dict[str, float] = {}
        self.panel_auth = self.registry.get_setting("panel_auth") == "true"

    # -- panel session auth --

    def _parse_header_value(self, request: bytes, name: str) -> str | None:
        for line in request.split(b"\r\n")[1:]:
            if b":" in line:
                key, value = line.split(b":", 1)
                if key.strip().lower() == name.encode().lower():
                    return value.strip().decode("latin-1")
        return None

    def _session_from_cookie(self, request: bytes) -> str | None:
        cookie = self._parse_header_value(request, "cookie")
        if not cookie:
            return None
        for part in cookie.split(";"):
            segment = part.strip()
            if segment.startswith("hopline_session="):
                return segment.split("=", 1)[1]
        return None

    def _valid_session(self, request: bytes) -> bool:
        token = self._session_from_cookie(request)
        if token is None:
            return False
        expiry = self._sessions.get(token, 0)
        if expiry < time.time():
            self._sessions.pop(token, None)
            return False
        return True

    def _is_api_path(self, method: str, path: str) -> bool:
        if path in {"/status", "/nodes", "/subscriptions", "/auth", "/service"}:
            return True
        if path.startswith("/sync") or path.startswith("/subscriptions/"):
            return True
        if path == "/nodes" or (path.startswith("/nodes/") and self._match_node_action(method, path) is not None):
            return True
        return False

    def _api_allowed(self, request: bytes) -> bool:
        if not self.panel_auth:
            return True
        if self._valid_session(request):
            return True
        auth = self._parse_header_value(request, "authorization")
        if not auth or not auth.lower().startswith("basic "):
            return False
        import base64, binascii, hmac
        try:
            decoded = base64.b64decode(auth[6:], validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            return False
        username, _, password = decoded.partition(":")
        stored_user, stored_pass = self._panel_credentials()
        return bool(username) and bool(password) and hmac.compare_digest(username, stored_user) and hmac.compare_digest(password, stored_pass)

    def _new_session(self) -> str:
        token = secrets.token_hex(24)
        self._sessions[token] = time.time() + 12 * 60 * 60
        return token

    def _panel_credentials(self) -> tuple[str, str]:
        username = self.registry.get_setting("auth_username") or ""
        password = self.registry.get_setting("auth_password") or ""
        return username, password

    async def _handle_panel_login(self, writer: asyncio.StreamWriter, reader: asyncio.StreamReader, request: bytes) -> None:
        if not self.panel_auth:
            await self._respond(writer, 200, {"ok": True})
            return
        length = self._content_length(request)
        body = await asyncio.wait_for(reader.readexactly(length), 2) if length else b""
        fields = parse_qs(body.decode("utf-8", "replace"))
        username = (fields.get("username") or [""])[0].strip()
        password = (fields.get("password") or [""])[0]
        stored_user, stored_pass = self._panel_credentials()
        import hmac
        if username == stored_user and password and hmac.compare_digest(password, stored_pass):
            token = self._new_session()
            writer.write(
                f"HTTP/1.1 302 Found\r\nSet-Cookie: hopline_session={token}; HttpOnly; SameSite=Strict; Path=/\r\n"
                f"Location: /\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode()
            )
            await writer.drain()
            return
        await self._respond_html(writer, 401, "login", "Invalid username or password")

    async def _handle_panel_logout(self, writer: asyncio.StreamWriter, request: bytes) -> None:
        token = self._session_from_cookie(request)
        if token:
            self._sessions.pop(token, None)
        writer.write(
            b"HTTP/1.1 302 Found\r\nSet-Cookie: hopline_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict\r\n"
            b"Location: /login\r\nContent-Length: 0\r\nConnection: close\r\n\r\n"
        )
        await writer.drain()

    async def _serve_login_page(self, writer: asyncio.StreamWriter) -> None:
        html = (
            "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<title>Hopline Login</title><style>"
            "body{background:#101314;color:#e8ece8;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;display:flex;align-items:center;justify-content:center;min-height:100dvh;margin:0}"
            ".card{border:1px solid #2c3433;padding:32px;width:min(360px,88vw);background:#171b1c}"
            "h1{font-size:18px;margin:0 0 4px}.sub{color:#8e9a95;font-size:12px;margin:0 0 20px}"
            "label{display:block;color:#8e9a95;font-size:10px;text-transform:uppercase;letter-spacing:.1em;margin:12px 0 4px}"
            "input{width:100%;box-sizing:border-box;background:#1d2324;border:1px solid #2c3433;color:#e8ece8;padding:10px 12px;font:inherit}"
            "button{width:100%;margin-top:20px;background:transparent;border:1px solid #d6a85c;color:#d6a85c;padding:10px;font:inherit;cursor:pointer}"
            ".err{color:#db7c71;font-size:12px;height:14px;margin-top:10px}</style></head><body>"
            "<form class='card' method='post' action='/panel/login'><h1>Hopline</h1><p class='sub'>Local egress control</p>"
            "<label for='u'>Username</label><input id='u' name='username' autocomplete='username' required>"
            "<label for='p'>Password</label><input id='p' name='password' type='password' autocomplete='current-password' required>"
            "<button type='submit'>Log in</button><div class='err'></div></form></body></html>"
        )
        await self._respond_html(writer, 200, "html", html)

    async def _respond_html(self, writer: asyncio.StreamWriter, status: int, content_type: str, body: str) -> None:
        payload = body.encode("utf-8") if status == 200 else body.encode("utf-8")
        reason = {200: "OK", 302: "Found", 401: "Unauthorized", 403: "Forbidden"}.get(status, "OK")
        ctype = "text/html; charset=utf-8" if content_type == "html" else content_type
        writer.write(
            f"HTTP/1.1 {status} {reason}\r\nContent-Type: {ctype}\r\n"
            f"Content-Length: {len(payload)}\r\nConnection: close\r\n\r\n".encode() + payload
        )
        await writer.drain()

    @property
    def port(self) -> int | None:
        sockets = self.server.sockets if self.server else None
        return sockets[0].getsockname()[1] if sockets else None

    async def start(self) -> None:
        if self.server is not None:
            raise RuntimeError("control API is already running")
        self.server = await asyncio.start_server(self._handle, self.host, self.requested_port)

    async def stop(self) -> None:
        if self.server is None:
            return
        self.server.close()
        await self.server.wait_closed()
        self.server = None

    def status(self) -> dict[str, Any]:
        nodes = self.registry.list_nodes()
        records = {record.node_id: record for record in self.registry.list_health()}
        geolocation = {row["node_id"]: row for row in self.registry.list_geolocation()}
        capabilities = {(row.node_id, row.family): row for row in self.registry.list_capabilities()}
        states = {state.value: 0 for state in HealthState}
        protocols: dict[str, dict[str, int]] = {}
        countries: dict[str, dict[str, int]] = {}
        for node in nodes:
            record = records.get(node.id)
            state = record.state.value if record else "unknown"
            states[state] = states.get(state, 0) + 1
            breakdown = protocols.setdefault(
                node.protocol,
                {"total": 0, **{health_state.value: 0 for health_state in HealthState}, "unknown": 0},
            )
            breakdown["total"] += 1
            breakdown[state] += 1
            geo = geolocation.get(node.id)
            country = str(geo["country_code"]).upper() if geo and geo["country_code"] else "unknown"
            country_breakdown = countries.setdefault(
                country,
                {"total": 0, **{health_state.value: 0 for health_state in HealthState}, "unknown": 0},
            )
            country_breakdown["total"] += 1
            country_breakdown[state] += 1
        return {
            "nodes": len(nodes),
            "health": states,
            "protocols": protocols,
            "countries": countries,
            "schema_version": self.registry.schema_version(),
        }

    def nodes(self) -> list[dict[str, Any]]:
        records = {record.node_id: record for record in self.registry.list_health()}
        geolocation = {row["node_id"]: row for row in self.registry.list_geolocation()}
        capabilities = {(row.node_id, row.family): row for row in self.registry.list_capabilities()}
        result = []
        for node in self.registry.list_nodes():
            record = records.get(node.id)
            geo = geolocation.get(node.id)
            result.append(
                {
                    "id": node.id,
                    "protocol": node.protocol,
                    "server": node.server,
                    "port": node.port,
                    "name": node.name,
                    "health": record.state.value if record else "unknown",
                    "successes": record.successes if record else 0,
                    "failures": record.failures if record else 0,
                    "latency_ms": record.latency_ms if record else None,
                    "performance": {
                        "conn_successes": record.conn_successes if record else 0,
                        "conn_failures": record.conn_failures if record else 0,
                        "latency_ewma_ms": record.latency_ewma_ms if record else None,
                        "success_rate": (
                            round(record.conn_successes / (record.conn_successes + record.conn_failures), 4)
                            if record and (record.conn_successes + record.conn_failures) else None
                        ),
                    },
                    "failure": (
                        {
                            "category": parse_legacy(record.failure_category).category,
                            "code": record.failure_category,
                        }
                        if record and record.failure_category else None
                    ),
                    "capabilities": {
                        family: {
                            "capable": record.ip is not None,
                            "ip": record.ip,
                            "checked_at": record.checked_at,
                            "last_error": record.last_error,
                        }
                        if (record := capabilities.get((node.id, family)))
                        else None
                        for family in ("ipv4", "ipv6")
                    },
                    "geolocation": (
                        {
                            "ip": geo["ip"],
                            "country_code": geo["country_code"],
                            "country": geo["country"],
                            "asn": geo["asn"],
                            "organization": geo["organization"],
                            "provider": geo["provider"],
                            "checked_at": geo["checked_at"],
                        }
                        if geo else None
                    ),
                }
            )
        return result

    def subscriptions(self) -> list[dict[str, Any]]:
        counts = self.registry.list_source_counts()
        managed = set(self.registry.list_managed_subscriptions())
        seen: set[str] = set()
        result = []

        def redacted(url: str) -> str:
            parsed = urlsplit(url)
            digest = hashlib.sha256(url.encode()).hexdigest()[:10]
            return f"{parsed.hostname or 'static'}#{digest}"

        for row in self.registry.list_subscriptions():
            source = row["source"]
            seen.add(source)
            parsed = urlsplit(source)
            digest = hashlib.sha256(source.encode()).hexdigest()[:10]
            result.append({
                "digest": digest,
                "source": redacted(source),
                "scheme": parsed.scheme or "static",
                "valid": bool(row["valid"]),
                "snapshot_hash": row["snapshot_hash"],
                "updated_at": row["updated_at"],
                "nodes": counts.get(source, 0),
            })
        for url in self.registry.list_managed_subscriptions():
            if url in seen:
                continue
            parsed = urlsplit(url)
            digest = hashlib.sha256(url.encode()).hexdigest()[:10]
            result.append({
                "digest": digest,
                "source": redacted(url),
                "scheme": parsed.scheme or "static",
                "valid": False,
                "snapshot_hash": None,
                "updated_at": None,
                "nodes": 0,
            })
        return result

    def auth(self) -> dict[str, Any]:
        username = self.registry.get_setting("auth_username")
        password = self.registry.get_setting("auth_password")
        return {
            "username": username or "",
            "password_set": bool(password),
        }

    async def _handle_auth(self, writer: asyncio.StreamWriter, reader: asyncio.StreamReader, request: bytes) -> None:
        if self._auth_callback is None:
            await self._respond(writer, 501, {"error": "not_implemented"})
            return
        length = self._content_length(request)
        body = await asyncio.wait_for(reader.readexactly(length), 2) if length else b""
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            await self._respond(writer, 400, {"error": "bad_request"})
            return
        username = str(payload.get("username", "")).strip()
        password = str(payload.get("password", ""))
        if not username or not password:
            await self._respond(writer, 400, {"error": "username_and_password_required"})
            return
        try:
            result = await self._auth_callback(username, password)
            await self._respond(writer, 200, result)
        except Exception as exc:
            await self._respond(writer, 502, {"error": type(exc).__name__})

    async def _handle_runtime(self, writer: asyncio.StreamWriter) -> None:
        if self._runtime_callback is None:
            await self._respond(writer, 501, {"error": "not_implemented"})
            return
        try:
            info = await self._runtime_callback()
            await self._respond(writer, 200, info)
        except Exception as exc:
            await self._respond(writer, 502, {"error": type(exc).__name__})

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 2)
            line = request.split(b"\r\n", 1)[0].decode("ascii", "replace")
            method, raw_path, _version = line.split(" ", 2)
            path = urlsplit(raw_path).path
            if method == "POST" and path == "/panel/login":
                await self._handle_panel_login(writer, reader, request)
            elif method == "POST" and path == "/panel/logout":
                await self._handle_panel_logout(writer, request)
            elif method == "GET" and path == "/login":
                await self._serve_login_page(writer)
            elif self._is_api_path(method, path) and not self._api_allowed(request):
                await self._respond(writer, 401, {"error": "unauthorized"})
            elif method == "POST" and path == "/sync":
                await self._handle_sync(writer)
            elif method == "POST" and path in {"/subscriptions/add", "/subscriptions/delete"}:
                await self._handle_subscription(writer, reader, request, path)
            elif method == "POST" and path == "/auth":
                await self._handle_auth(writer, reader, request)
            elif self._match_node_action(method, path) is not None:
                node_id, action = self._match_node_action(method, path)
                await self._handle_node_action(writer, node_id, action)
            elif method != "GET":
                await self._respond(writer, 405, {"error": "method_not_allowed"})
            elif path == "/status":
                await self._respond(writer, 200, self.status())
            elif path == "/nodes":
                await self._respond(writer, 200, {"nodes": self.nodes()})
            elif path == "/subscriptions":
                await self._respond(writer, 200, {"subscriptions": self.subscriptions()})
            elif path == "/auth":
                await self._respond(writer, 200, self.auth())
            elif path == "/service":
                await self._handle_runtime(writer)
            elif self.static_dir is not None:
                if self.panel_auth and not self._valid_session(request):
                    await self._serve_login_page(writer)
                else:
                    await self._respond_static(writer, path)
            else:
                await self._respond(writer, 404, {"error": "not_found"})
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, ValueError):
            await self._respond(writer, 400, {"error": "bad_request"})
        finally:
            writer.close()
            await writer.wait_closed()

    @staticmethod
    def _content_length(request: bytes) -> int:
        for header in request.split(b"\r\n")[1:]:
            if b":" in header:
                key, value = header.split(b":", 1)
                if key.strip().lower() == b"content-length":
                    try:
                        return int(value.strip())
                    except ValueError:
                        return 0
        return 0

    async def _handle_subscription(self, writer: asyncio.StreamWriter, reader: asyncio.StreamReader, request: bytes, path: str) -> None:
        if self._subscription_callback is None:
            await self._respond(writer, 501, {"error": "not_implemented"})
            return
        length = self._content_length(request)
        body = await asyncio.wait_for(reader.readexactly(length), 2) if length else b""
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            await self._respond(writer, 400, {"error": "bad_request"})
            return
        action = "add" if path.endswith("/add") else "delete"
        try:
            result = await self._subscription_callback(action, payload)
            await self._respond(writer, 200, result)
        except ValueError as exc:
            await self._respond(writer, 404, {"error": str(exc)})
        except Exception as exc:
            await self._respond(writer, 502, {"error": type(exc).__name__})

    async def _handle_sync(self, writer: asyncio.StreamWriter) -> None:
        if self._sync_callback is None:
            await self._respond(writer, 501, {"error": "not_implemented"})
            return
        try:
            results = await self._sync_callback()
            await self._respond(writer, 200, {"synced": len(results)})
        except Exception as exc:
            await self._respond(writer, 502, {"error": type(exc).__name__})

    _NODE_ACTIONS = frozenset({"enable", "disable", "probe"})

    @classmethod
    def _match_node_action(cls, method: str, path: str) -> tuple[str, str] | None:
        if method != "POST":
            return None
        parts = path.split("/")
        if len(parts) == 4 and parts[1] == "nodes" and parts[2] and parts[3] in cls._NODE_ACTIONS:
            return parts[2], parts[3]
        return None

    async def _handle_node_action(self, writer: asyncio.StreamWriter, node_id: str, action: str) -> None:
        if self._node_action_callback is None:
            await self._respond(writer, 501, {"error": "not_implemented"})
            return
        try:
            result = await self._node_action_callback(node_id, action)
            await self._respond(writer, 200, result)
        except ValueError as exc:
            await self._respond(writer, 404, {"error": str(exc)})
        except Exception as exc:
            await self._respond(writer, 502, {"error": type(exc).__name__})

    async def _respond_static(self, writer: asyncio.StreamWriter, path: str) -> None:
        if self.static_dir is None:
            await self._respond(writer, 404, {"error": "not_found"})
            return
        relative = unquote(path).lstrip("/")
        candidate = (self.static_dir / relative).resolve()
        try:
            candidate.relative_to(self.static_dir)
        except ValueError:
            await self._respond(writer, 404, {"error": "not_found"})
            return
        if not candidate.is_file():
            candidate = self.static_dir / "index.html"
        if not candidate.is_file():
            await self._respond(writer, 404, {"error": "ui_not_built"})
            return
        body = await asyncio.to_thread(candidate.read_bytes)
        content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        writer.write(
            f"HTTP/1.1 200 OK\r\nContent-Type: {content_type}; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\nCache-Control: no-store\r\nConnection: close\r\n\r\n".encode() + body
        )
        await writer.drain()

    @staticmethod
    async def _respond(writer: asyncio.StreamWriter, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        reason = {200: "OK", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found", 405: "Method Not Allowed", 501: "Not Implemented", 502: "Bad Gateway"}[status]
        writer.write(
            f"HTTP/1.1 {status} {reason}\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode() + body
        )
        await writer.drain()
