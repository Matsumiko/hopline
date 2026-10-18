from __future__ import annotations

from typing import Any

from .models import Node

UTLS_FINGERPRINTS = frozenset(
    {"chrome", "firefox", "safari", "ios", "android", "edge", "360", "qq", "random", "randomized"}
)


def normalize_fingerprint(value: str | None, *, reality: bool = False) -> str | None:
    """Map a provider fingerprint onto a uTLS profile sing-box accepts.

    Providers reuse v2ray flags such as ``unsafe`` that sing-box rejects as an unknown
    fingerprint. Unsupported values fall back to the default profile, or to no uTLS at
    all when the node does not require Reality.
    """
    if value:
        candidate = value.strip().lower()
        if candidate in UTLS_FINGERPRINTS:
            return candidate
    return "chrome" if reality else None


def _outbound(node: Node) -> dict[str, Any]:
    outbound_type = "shadowsocks" if node.protocol == "ss" else node.protocol
    outbound: dict[str, Any] = {
        "type": outbound_type,
        "tag": node.id,
        "server": node.server,
        "server_port": node.port,
        "domain_resolver": "dns-direct",
    }
    if node.protocol in {"vless", "vmess"}:
        outbound["uuid"] = node.uuid
    elif node.protocol == "trojan":
        outbound["password"] = node.uuid
    elif node.protocol == "ss":
        outbound["method"] = node.method or "chacha20-ietf-poly1305"
        outbound["password"] = node.uuid
        if node.plugin:
            outbound["plugin"] = node.plugin
        if node.plugin_opts:
            outbound["plugin_opts"] = node.plugin_opts
    else:
        raise ValueError(f"unsupported outbound protocol: {node.protocol}")
    if node.protocol == "vmess":
        if node.security:
            outbound["security"] = node.security
        outbound["alter_id"] = node.alter_id if node.alter_id is not None else 0
        outbound["packet_encoding"] = node.packet_encoding or "xudp"
        if node.global_padding is not None:
            outbound["global_padding"] = node.global_padding
        if node.authenticated_length is not None:
            outbound["authenticated_length"] = node.authenticated_length
    if node.protocol == "vless":
        outbound["packet_encoding"] = node.packet_encoding or "xudp"
        flow = node.flow or ""
        if flow.endswith("-udp443"):
            flow = flow[:-7]
        if flow and flow != "none":
            outbound["flow"] = flow
        if node.encryption and node.encryption != "none":
            outbound["encryption"] = node.encryption
    if node.tls and node.protocol != "ss":
        tls: dict[str, Any] = {"enabled": True, "server_name": node.sni or node.server}
        if node.allow_insecure:
            tls["insecure"] = True
        if node.alpn:
            tls["alpn"] = [item for item in node.alpn.split(",") if item]
        if node.reality_pbk:
            tls["reality"] = {
                "enabled": True,
                "public_key": node.reality_pbk,
                **({"short_id": node.reality_sid.split(",")[0]} if node.reality_sid else {}),
            }
        fingerprint = normalize_fingerprint(node.fingerprint, reality=bool(node.reality_pbk))
        if fingerprint:
            tls["utls"] = {"enabled": True, "fingerprint": fingerprint}
        outbound["tls"] = tls
    if node.transport_type and node.transport_type != "tcp" and node.protocol != "ss":
        network = node.transport_type
        transport: dict[str, Any] = {"type": network}
        if network == "ws":
            path = node.path or "/"
            if "?ed=" in path:
                path, early_data = path.split("?ed=", 1)
                try:
                    early_length = int(early_data)
                except ValueError:
                    early_length = 0
                if early_length > 0:
                    transport["max_early_data"] = early_length
                    transport["early_data_header_name"] = "Sec-WebSocket-Protocol"
            transport["path"] = path or "/"
            if node.host:
                transport["headers"] = {"Host": node.host}
        elif network == "grpc":
            if node.service_name or node.path:
                transport["service_name"] = node.service_name or node.path
        elif network == "http":
            if node.path:
                transport["path"] = node.path
            if node.host:
                transport["host"] = [item for item in node.host.split(",") if item]
        elif network == "httpupgrade":
            if node.path:
                transport["path"] = node.path
            if node.host:
                transport["host"] = node.host
        if node.header_type == "http" and network == "tcp":
            transport = {"type": "http", "method": "GET", "path": node.path or "/"}
            if node.host:
                transport["headers"] = {"Host": node.host}
        outbound["transport"] = transport
    elif node.header_type == "http" and node.protocol != "ss":
        outbound["transport"] = {
            "type": "http", "method": "GET", "path": node.path or "/",
            **({"headers": {"Host": node.host}} if node.host else {}),
        }
    return outbound


def _dns_config(nodes: list[Node]) -> dict[str, Any]:
    relay_domains = sorted({node.server for node in nodes if node.server})
    remote_servers = [
        {
            "type": "tls",
            "tag": f"dns-remote-{node.id}",
            "server": "8.8.8.8",
            "detour": node.id,
            "domain_resolver": "dns-direct",
        }
        for node in nodes
    ]
    remote_rules = [
        {"auth_user": [node.id], "server": f"dns-remote-{node.id}"}
        for node in nodes
    ]
    return {
        "servers": remote_servers + [{"type": "local", "tag": "dns-direct"}],
        "rules": (
            ([{"action": "route", "domain": relay_domains, "server": "dns-direct"}]
             if relay_domains else [])
            + remote_rules
        ),
        "final": "dns-direct",
    }


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
        {"action": "sniff", "inbound": ["mixed-in"]},
        {"action": "hijack-dns", "protocol": "dns"},
        *(
            {
                "inbound": ["mixed-in"],
                "auth_user": [node.id],
                "outbound": node.id,
            }
            for node in nodes
        ),
    ]
    node_outbounds = [_outbound(node) for node in nodes]
    node_tags = [node.id for node in nodes]
    return {
        "log": {"level": "error"},
        "dns": _dns_config(nodes),
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": listen_port,
                "users": users,
            }
        ],
        "outbounds": node_outbounds
        + [
            {
                "type": "selector",
                "tag": "proxy-auto",
                "outbounds": node_tags,
                "default": node_tags[0],
            },
            {"type": "direct", "tag": "direct"},
        ],
        "route": {
            "rules": rules,
            "final": "proxy-auto",
            "default_domain_resolver": "dns-direct",
        },
    }
