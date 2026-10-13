from __future__ import annotations

from typing import Any

from .models import Node


def _outbound(node: Node) -> dict[str, Any]:
    outbound: dict[str, Any] = {
        "type": node.protocol,
        "tag": node.id,
        "server": node.server,
        "server_port": node.port,
        "uuid": node.uuid,
    }
    if node.tls:
        outbound["tls"] = {"enabled": True, "server_name": node.sni or node.server}
    if node.transport_type and node.transport_type != "tcp":
        transport: dict[str, Any] = {"type": node.transport_type}
        if node.path:
            transport["path"] = node.path
        if node.host:
            transport["headers"] = {"Host": node.host}
        outbound["transport"] = transport
    return outbound


def build_config(
    nodes: list[Node],
    *,
    listen_port: int,
    credentials: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not nodes:
        raise ValueError("at least one node is required")
    if not 1 <= listen_port <= 65535:
        raise ValueError("listen port is out of range")
    credentials = credentials or {node.id: node.credential for node in nodes}
    users = [
        {"username": node.id, "password": credentials[node.id]}
        for node in nodes
    ]
    rules = [
        {
            "inbound": ["mixed-in"],
            "auth_user": [node.id],
            "outbound": node.id,
        }
        for node in nodes
    ]
    return {
        "log": {"level": "error"},
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": listen_port,
                "users": users,
            }
        ],
        "outbounds": [_outbound(node) for node in nodes]
        + [{"type": "direct", "tag": "direct"}],
        "route": {"rules": rules, "final": "direct"},
    }
