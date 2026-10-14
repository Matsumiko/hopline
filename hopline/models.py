from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    protocol: str
    server: str
    port: int
    uuid: str
    tls: bool = False
    sni: str | None = None
    transport_type: str | None = None
    path: str | None = None
    host: str | None = None
    method: str | None = None
    plugin: str | None = None
    plugin_opts: str | None = None
    security: str | None = None
    encryption: str | None = None
    global_padding: bool | None = None
    authenticated_length: bool | None = None
    alter_id: int | None = None
    packet_encoding: str | None = None
    flow: str | None = None
    reality_pbk: str | None = None
    reality_sid: str | None = None
    reality_spx: str | None = None
    fingerprint: str | None = None
    alpn: str | None = None
    allow_insecure: bool = False
    service_name: str | None = None
    header_type: str | None = None
    name: str | None = None
    @property
    def credential(self) -> str:
        return self.uuid
