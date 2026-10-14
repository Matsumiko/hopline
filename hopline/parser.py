from __future__ import annotations

import base64
import binascii
import hashlib
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import UUID

from .models import Node


def _query_one(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def _node_id(
    protocol: str,
    server: str,
    port: int,
    credential: str,
    security: str,
    sni: str | None,
    transport_type: str,
    path: str | None,
    host: str | None,
    method: str | None,
    plugin: str | None = None,
    plugin_opts: str | None = None,
) -> str:
    identity = "|".join(
        (
            protocol, server.lower(), str(port), credential, security,
            sni or "", transport_type, path or "", host or "", method or "",
            plugin or "", plugin_opts or "",
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]


def parse_share_link(link: str, *, source: str | None = None) -> Node:
    parsed = urlsplit(link)
    protocol = parsed.scheme.lower()
    if protocol not in {"vless", "trojan", "vmess", "ss"}:
        raise ValueError("unsupported share-link protocol")
    if not parsed.hostname or parsed.port is None:
        raise ValueError("share link requires host and port")
    if parsed.port < 1 or parsed.port > 65535:
        raise ValueError("share-link port is out of range")
    query = parse_qs(parsed.query, keep_blank_values=True)
    security = _query_one(query, "security") or "none"
    transport_type = _query_one(query, "type") or "tcp"
    sni = _query_one(query, "sni") or parsed.hostname
    path = _query_one(query, "path")
    host = _query_one(query, "host")
    name = unquote(parsed.fragment) or None
    method: str | None = None
    plugin: str | None = None
    plugin_opts: str | None = None
    security_option = _query_one(query, "encryption") or _query_one(query, "security") or "none"
    global_padding_raw = _query_one(query, "global_padding")
    authenticated_length_raw = _query_one(query, "authenticated_length")
    global_padding = None if global_padding_raw is None else global_padding_raw.lower() == "true"
    authenticated_length = None if authenticated_length_raw is None else authenticated_length_raw.lower() == "true"
    plugin_value = _query_one(query, "plugin")
    if plugin_value:
        plugin_parts = plugin_value.split(";", 1)
        plugin = plugin_parts[0] or None
        plugin_opts = plugin_parts[1] if len(plugin_parts) == 2 else None
    if protocol == "ss":
        if not parsed.username:
            raise ValueError("Shadowsocks link requires encoded method and password")
        try:
            encoded = unquote(parsed.username)
            padded = encoded + "=" * (-len(encoded) % 4)
            decoded = base64.urlsafe_b64decode(padded).decode("utf-8")
            method, credential = decoded.split(":", 1)
        except (binascii.Error, UnicodeError, ValueError) as exc:
            raise ValueError("Shadowsocks credentials are invalid") from exc
    else:
        if not parsed.username:
            raise ValueError(f"{protocol.upper()} link requires UUID")
        try:
            credential = str(UUID(unquote(parsed.username)))
        except ValueError as exc:
            raise ValueError(f"{protocol.upper()} UUID is invalid") from exc

    node_id = _node_id(
        protocol, parsed.hostname, parsed.port, credential, security,
        sni, transport_type, path, host, method, plugin, plugin_opts,
    )
    return Node(
        id=node_id,
        protocol=protocol,
        server=parsed.hostname,
        port=parsed.port,
        uuid=credential,
        tls=security == "tls" or protocol in {"trojan", "vmess", "ss"},
        sni=sni,
        transport_type=transport_type,
        path=path,
        host=host,
        method=method,
        plugin=plugin,
        plugin_opts=plugin_opts,
        security=security_option,
        global_padding=global_padding,
        authenticated_length=authenticated_length,
        name=name,
    )


def parse_vless(link: str, *, source: str | None = None) -> Node:
    node = parse_share_link(link, source=source)
    if node.protocol != "vless":
        raise ValueError("unsupported share-link protocol")
    return node

def parse_structured_subscription(body: bytes, *, source: str | None = None) -> list[Node]:
    """Parse sing-box JSON or Clash YAML without exposing credentials."""
    import json

    try:
        document = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        try:
            import yaml
        except ImportError as exc:
            raise ValueError("Clash YAML requires PyYAML") from exc
        try:
            document = yaml.safe_load(body.decode("utf-8"))
        except (UnicodeDecodeError, yaml.YAMLError) as exc:
            raise ValueError("structured subscription is invalid") from exc
    if not isinstance(document, dict):
        raise ValueError("structured subscription must be an object")
    entries = document.get("outbounds") or document.get("proxies")
    if not isinstance(entries, list):
        raise ValueError("structured subscription has no outbounds or proxies")
    nodes: list[Node] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            node = _parse_structured_node(entry, source=source)
        except (TypeError, ValueError, KeyError):
            continue
        if node is not None:
            nodes.append(node)
    return nodes


def _parse_structured_node(entry: dict[str, object], *, source: str | None) -> Node | None:
    protocol = str(entry.get("type", "")).lower()
    if protocol == "shadowsocks":
        protocol = "ss"
    if protocol not in {"vless", "vmess", "trojan", "ss"}:
        return None
    server = str(entry["server"])
    port = int(entry.get("server_port", entry.get("port")))
    if not server or not 1 <= port <= 65535:
        raise ValueError("structured node host or port is invalid")
    credential = str(entry.get("uuid", entry.get("password", "")))
    method = str(entry.get("method", entry.get("cipher", ""))) or None
    if not credential:
        raise ValueError("structured node credential is missing")
    tls_data = entry.get("tls")
    tls = bool(tls_data) if isinstance(tls_data, bool) else bool(isinstance(tls_data, dict) and tls_data.get("enabled"))
    sni = str(entry.get("servername", entry.get("server_name", server)))
    if isinstance(tls_data, dict):
        sni = str(tls_data.get("server_name", sni))
    transport_data = entry.get("transport")
    ws_data = entry.get("ws-opts")
    transport_type = str(entry.get("network", "tcp"))
    path = None
    host = None
    if isinstance(transport_data, dict):
        transport_type = str(transport_data.get("type", transport_type))
        path = transport_data.get("path")
        headers = transport_data.get("headers")
        host = headers.get("Host") if isinstance(headers, dict) else None
    if isinstance(ws_data, dict):
        transport_type = "ws"
        path = ws_data.get("path")
        headers = ws_data.get("headers")
        host = headers.get("Host") if isinstance(headers, dict) else host
    name = str(entry.get("tag", entry.get("name", ""))) or None
    security = str(entry.get("security", "tls" if tls else "none"))
    global_padding = entry.get("global_padding")
    authenticated_length = entry.get("authenticated_length")
    return Node(
        id=_node_id(protocol, server, port, credential, security, sni, transport_type, str(path) if path else None, str(host) if host else None, method),
        protocol=protocol, server=server, port=port, uuid=credential, tls=tls,
        sni=sni, transport_type=transport_type, path=str(path) if path else None,
        host=str(host) if host else None, method=method, security=security,
        global_padding=bool(global_padding) if global_padding is not None else None,
        authenticated_length=bool(authenticated_length) if authenticated_length is not None else None,
        name=name,
    )
