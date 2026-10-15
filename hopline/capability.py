from __future__ import annotations

import ipaddress
import time
from dataclasses import dataclass


FAMILIES = ("ipv4", "ipv6")


@dataclass(frozen=True, slots=True)
class CapabilityRecord:
    node_id: str
    family: str
    ip: str | None
    checked_at: float
    last_error: str | None = None

    @property
    def capable(self) -> bool:
        return self.ip is not None

    def is_fresh(self, *, now: float | None = None, max_age: float) -> bool:
        if max_age <= 0:
            raise ValueError("capability max_age must be positive")
        current = time.time() if now is None else now
        return 0 <= current - self.checked_at <= max_age


def family_for_ip(value: str) -> str:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise ValueError("capability IP is invalid") from error
    return "ipv4" if address.version == 4 else "ipv6"
