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
    global_padding: bool | None = None
    authenticated_length: bool | None = None
    name: str | None = None
    @property
    def credential(self) -> str:
        return self.uuid
