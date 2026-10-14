from __future__ import annotations

import base64
import binascii
import hashlib
import json
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import UUID

from .models import Node


def _decode_base64_json(value: str) -> dict[str, object] | None:
    try:
        normalized = value.split("#", 1)[0].replace("-", "+").replace("_", "/")
        decoded = base64.b64decode(normalized + "=" * (-len(normalized) % 4)).decode("utf-8")
        data = json.loads(decoded)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _bool_query(query: dict[str, list[str]], key: str) -> bool | None:
    value = _query_one(query, key)
    if value is None:
        return None
    return value.lower() in {"1", "true", "yes"}


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
    alter_id: int | None = None,
    packet_encoding: str | None = None,
    flow: str | None = None,
    reality_pbk: str | None = None,
    reality_sid: str | None = None,
    fingerprint: str | None = None,
    alpn: str | None = None,
    allow_insecure: bool = False,
) -> str:
    identity = "|".join(
        (
            protocol, server.lower(), str(port), credential, security,
            sni or "", transport_type, path or "", host or "", method or "",
            plugin or "", plugin_opts or "", str(alter_id) if alter_id is not None else "",
            packet_encoding or "", flow or "", reality_pbk or "", reality_sid or "",
            fingerprint or "", alpn or "", str(allow_insecure),
        )
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]


def _bool_value(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes"}


def parse_share_link(link: str, *, source: str | None = None) -> Node:
    parsed = urlsplit(link)
    protocol = parsed.scheme.lower()
    if protocol not in {"vless", "trojan", "vmess", "ss"}:
        raise ValueError("unsupported share-link protocol")
    if protocol == "vmess":
        value = _decode_base64_json(parsed.netloc + parsed.path)
        if value is not None:
            server = str(value.get("add", value.get("server", "")))
            if not server:
                raise ValueError("VMess link requires host")
            try:
                port = int(value.get("port", 443))
            except (TypeError, ValueError) as exc:
                raise ValueError("VMess port is invalid") from exc
            credential = str(value.get("id", ""))
            try:
                credential = str(UUID(credential))
            except ValueError as exc:
                raise ValueError("VMess UUID is invalid") from exc
            transport_type = str(value.get("net", "tcp"))
            if transport_type == "h2":
                transport_type = "http"
            path = str(value.get("path", "")) or None
            host = str(value.get("host", "")) or None
            sni = str(value.get("sni", "")) or server
            tls_value = str(value.get("tls", "")).lower()
            security = str(value.get("scy", "auto")) or "auto"
            alter_id = int(value.get("aid", 0) or 0)
            packet_encoding = str(value.get("packet_encoding", value.get("packetEncoding", ""))) or None
            flow = str(value.get("flow", "")) or None
            name = unquote(parsed.fragment) or str(value.get("ps", "")) or None
            node_id = _node_id(
                protocol, server, port, credential, security, sni, transport_type,
                path, host, None, None, None, alter_id, packet_encoding, flow,
            )
            return Node(
                id=node_id, protocol=protocol, server=server, port=port, uuid=credential,
                tls=tls_value in {"tls", "reality"}, sni=sni, transport_type=transport_type,
                path=path, host=host, security=security, encryption=security,
                alter_id=alter_id, packet_encoding=packet_encoding, flow=flow, name=name,
                global_padding=_bool_value(value.get("global_padding", value.get("globalPadding"))),
                authenticated_length=_bool_value(value.get("authenticated_length", value.get("authenticatedLength"))),
            )
    if not parsed.hostname or parsed.port is None:
        raise ValueError("share link requires host and port")
    if parsed.port < 1 or parsed.port > 65535:
        raise ValueError("share-link port is out of range")
    query = parse_qs(parsed.query, keep_blank_values=True)
    security = _query_one(query, "security") or "none"
    if transport_type := _query_one(query, "type"):
        transport_type = "http" if transport_type == "h2" else transport_type
    else:
        transport_type = "tcp"
    sni = _query_one(query, "sni") or _query_one(query, "peer") or parsed.hostname
    path = _query_one(query, "path")
    host = _query_one(query, "host")
    service_name = _query_one(query, "serviceName")
    if transport_type == "grpc":
        path = service_name or path
    header_type = _query_one(query, "headerType")
    name = unquote(parsed.fragment) or None
    method: str | None = None
    plugin: str | None = None
    plugin_opts: str | None = None
    encryption = _query_one(query, "encryption")
    security_option = (
        encryption or "auto" if protocol == "vmess"
        else encryption or security or "none"
    )
    global_padding = _bool_query(query, "global_padding")
    authenticated_length = _bool_query(query, "authenticated_length")
    alter_id_raw = _query_one(query, "alter_id") or _query_one(query, "aid")
    alter_id = int(alter_id_raw) if alter_id_raw and alter_id_raw.isdigit() else None
    packet_encoding = _query_one(query, "packetEncoding") or _query_one(query, "packet_encoding")
    if protocol == "vless" and not packet_encoding:
        packet_encoding = "xudp"
    flow = _query_one(query, "flow")
    plugin_value = _query_one(query, "plugin")
    if plugin_value:
        plugin_parts = plugin_value.split(";", 1)
        plugin = plugin_parts[0] or None
        plugin_opts = plugin_parts[1] if len(plugin_parts) == 2 else None
    reality_pbk = _query_one(query, "pbk")
    reality_sid = _query_one(query, "sid")
    reality_spx = _query_one(query, "spx")
    fingerprint = _query_one(query, "fp")
    alpn = _query_one(query, "alpn")
    allow_insecure = _bool_query(query, "allowInsecure")
    if allow_insecure is None:
        allow_insecure = _bool_query(query, "insecure") or False
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
        if protocol == "trojan":
            credential = unquote(parsed.username or parsed.path.lstrip("/"))
            if not credential:
                raise ValueError("TROJAN link requires password")
        else:
            if not parsed.username:
                raise ValueError(f"{protocol.upper()} link requires UUID")
            try:
                credential = str(UUID(unquote(parsed.username)))
            except ValueError as exc:
                raise ValueError(f"{protocol.upper()} UUID is invalid") from exc
    tls = security in {"tls", "reality"} or protocol == "trojan"
    node_id = _node_id(
        protocol, parsed.hostname, parsed.port, credential, security, sni,
        transport_type, path, host, method, plugin, plugin_opts, alter_id,
        packet_encoding, flow, reality_pbk, reality_sid, fingerprint, alpn,
        allow_insecure,
    )
    return Node(
        id=node_id, protocol=protocol, server=parsed.hostname, port=parsed.port,
        uuid=credential, tls=tls, sni=sni, transport_type=transport_type,
        path=path, host=host, method=method, plugin=plugin, plugin_opts=plugin_opts,
        security=security_option, encryption=encryption,
        global_padding=global_padding, authenticated_length=authenticated_length,
        alter_id=alter_id, packet_encoding=packet_encoding, flow=flow,
        reality_pbk=reality_pbk, reality_sid=reality_sid, reality_spx=reality_spx,
        fingerprint=fingerprint, alpn=alpn, allow_insecure=allow_insecure,
        service_name=service_name, header_type=header_type, name=name,
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
    reality_pbk = reality_sid = reality_spx = fingerprint = alpn = None
    allow_insecure = False
    if isinstance(tls_data, dict):
        sni = str(tls_data.get("server_name", sni))
        allow_insecure = bool(tls_data.get("insecure", False))
        raw_alpn = tls_data.get("alpn")
        alpn = ",".join(str(item) for item in raw_alpn) if isinstance(raw_alpn, list) else str(raw_alpn or "") or None
        reality_data = tls_data.get("reality")
        if isinstance(reality_data, dict):
            reality_pbk = str(reality_data.get("public_key", "")) or None
            reality_sid = str(reality_data.get("short_id", "")) or None
        utls_data = tls_data.get("utls")
        if isinstance(utls_data, dict):
            fingerprint = str(utls_data.get("fingerprint", "")) or None
    transport_data = entry.get("transport")
    ws_data = entry.get("ws-opts")
    transport_type = str(entry.get("network", "tcp"))
    path = None
    host = None
    service_name = None
    if isinstance(transport_data, dict):
        transport_type = str(transport_data.get("type", transport_type))
        path = transport_data.get("path")
        service_name = transport_data.get("service_name")
        headers = transport_data.get("headers")
        host = headers.get("Host") if isinstance(headers, dict) else None
    if isinstance(ws_data, dict):
        transport_type = "ws"
        path = ws_data.get("path")
        headers = ws_data.get("headers")
        host = headers.get("Host") if isinstance(headers, dict) else host
    name = str(entry.get("tag", entry.get("name", ""))) or None
    security = str(entry.get("security", "tls" if tls else "none"))
    encryption = str(entry.get("encryption", "")) or None
    global_padding = entry.get("global_padding")
    authenticated_length = entry.get("authenticated_length")
    alter_id = entry.get("alter_id", entry.get("alterId"))
    packet_encoding = entry.get("packet_encoding", entry.get("packetEncoding"))
    flow = entry.get("flow")
    header_type = entry.get("header_type")
    alter_id_value = int(alter_id) if alter_id is not None else None
    packet_encoding_value = str(packet_encoding) if packet_encoding else None
    flow_value = str(flow) if flow else None
    return Node(
        id=_node_id(
            protocol, server, port, credential, security, sni,
            transport_type, str(path) if path else None, str(host) if host else None,
            method, alter_id=alter_id_value, packet_encoding=packet_encoding_value,
            flow=flow_value, reality_pbk=reality_pbk, reality_sid=reality_sid,
            fingerprint=fingerprint, alpn=alpn, allow_insecure=allow_insecure,
        ),
        protocol=protocol, server=server, port=port, uuid=credential, tls=tls,
        sni=sni, transport_type=transport_type, path=str(path) if path else None,
        host=str(host) if host else None, method=method, security=security,
        encryption=encryption, alter_id=alter_id_value, packet_encoding=packet_encoding_value,
        flow=flow_value, reality_pbk=reality_pbk, reality_sid=reality_sid,
        reality_spx=reality_spx, fingerprint=fingerprint, alpn=alpn,
        allow_insecure=allow_insecure, service_name=str(service_name) if service_name else None,
        header_type=str(header_type) if header_type else None,
        global_padding=_bool_value(global_padding), authenticated_length=_bool_value(authenticated_length),
        name=name,
    )
