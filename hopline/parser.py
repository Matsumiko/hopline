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
) -> str:
    identity = "|".join(
        (
            protocol, server.lower(), str(port), credential, security,
            sni or "", transport_type, path or "", host or "", method or "",
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
        sni, transport_type, path, host, method,
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
        name=name,
    )


def parse_vless(link: str, *, source: str | None = None) -> Node:
    node = parse_share_link(link, source=source)
    if node.protocol != "vless":
        raise ValueError("unsupported share-link protocol")
    return node
