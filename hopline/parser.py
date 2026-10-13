from __future__ import annotations

import hashlib
from urllib.parse import parse_qs, unquote, urlsplit
from uuid import UUID

from .models import Node


def _query_one(query: dict[str, list[str]], key: str) -> str | None:
    values = query.get(key)
    return values[0] if values else None


def parse_vless(link: str, *, source: str | None = None) -> Node:
    parsed = urlsplit(link)
    if parsed.scheme.lower() != "vless":
        raise ValueError("unsupported share-link protocol")
    if not parsed.hostname or parsed.port is None or not parsed.username:
        raise ValueError("VLESS link requires UUID, host, and port")
    try:
        uuid = str(UUID(unquote(parsed.username)))
    except ValueError as exc:
        raise ValueError("VLESS UUID is invalid") from exc
    if parsed.port < 1 or parsed.port > 65535:
        raise ValueError("VLESS port is out of range")

    query = parse_qs(parsed.query, keep_blank_values=True)
    security = _query_one(query, "security") or "none"
    transport_type = _query_one(query, "type") or "tcp"
    sni = _query_one(query, "sni") or parsed.hostname
    path = _query_one(query, "path")
    host = _query_one(query, "host")
    name = unquote(parsed.fragment) or None
    identity = "|".join(
        (
            "vless",
            parsed.hostname.lower(),
            str(parsed.port),
            uuid,
            security,
            sni or "",
            transport_type,
            path or "",
            host or "",
        )
    )
    node_id = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return Node(
        id=node_id,
        protocol="vless",
        server=parsed.hostname,
        port=parsed.port,
        uuid=uuid,
        tls=security == "tls",
        sni=sni,
        transport_type=transport_type,
        path=path,
        host=host,
        name=name,
    )
