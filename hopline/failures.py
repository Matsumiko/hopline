from __future__ import annotations

import re
from dataclasses import dataclass

# Failure categories. Values are stable machine-readable codes; never free text.
CONNECT_TIMEOUT = "connect_timeout"
CONNECT_REFUSED = "connect_refused"
CONNECT_RESET = "connect_reset"
TLS_ERROR = "tls_error"
HANDSHAKE_TIMEOUT = "handshake_timeout"
AUTH_REJECTED = "auth_rejected"
UPSTREAM_REJECTED = "upstream_rejected"
PROBE_TIMEOUT = "probe_timeout"
PROBE_FAILED = "probe_failed"
NODE_MISMATCH = "node_mismatch"
IO_ERROR = "io_error"
UNKNOWN = "unknown"

CATEGORIES = frozenset(
    {
        CONNECT_TIMEOUT, CONNECT_REFUSED, CONNECT_RESET, TLS_ERROR, HANDSHAKE_TIMEOUT,
        AUTH_REJECTED, UPSTREAM_REJECTED, PROBE_TIMEOUT, PROBE_FAILED, NODE_MISMATCH,
        IO_ERROR, UNKNOWN,
    }
)

_SENSITIVE = re.compile(
    r"(?:(?:proxy-authorization|authorization)\s*[:=]\s*(?:basic|bearer)?\s*\S+)"
    r"|(?:\bbasic\s+[A-Za-z0-9+/=]{8,})"
    r"|(?:(?:vless|vmess|trojan|ss|socks)://\S+)"
    r"|(?:\b(?:password|passwd|secret|token|apikey|api[_-]?key)\b\s*[:=]\s*\S+)"
    r"|(?:\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b)"
    r"|(?:\b[A-Za-z0-9+/]{16,}={0,2}\b)",
    re.IGNORECASE,
)


def redact(text: str, limit: int = 200) -> str:
    """Strip credentials and share links from any operator-visible string."""
    if not text:
        return ""
    cleaned = _SENSITIVE.sub("[redacted]", text)
    return cleaned[:limit]


@dataclass(frozen=True, slots=True)
class FailureReason:
    """Structured failure cause: a stable category plus a redacted detail."""

    category: str
    detail: str = ""

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            object.__setattr__(self, "category", UNKNOWN)
        object.__setattr__(self, "detail", redact(self.detail, 120))

    @property
    def code(self) -> str:
        return f"{self.category}:{self.detail}" if self.detail else self.category

    def as_dict(self) -> dict[str, str]:
        return {"category": self.category, "detail": self.detail}


def classify_exception(error: BaseException) -> FailureReason:
    """Map an exception to a stable category without leaking its message."""
    import asyncio
    import ssl

    name = type(error).__name__
    if isinstance(error, asyncio.TimeoutError) or name == "TimeoutError":
        return FailureReason(CONNECT_TIMEOUT)
    if isinstance(error, ssl.SSLError):
        return FailureReason(TLS_ERROR, name)
    if isinstance(error, ConnectionRefusedError):
        return FailureReason(CONNECT_REFUSED)
    if isinstance(error, ConnectionResetError):
        return FailureReason(CONNECT_RESET)
    if isinstance(error, (ConnectionError, OSError)):
        return FailureReason(IO_ERROR, name)
    if isinstance(error, asyncio.IncompleteReadError):
        return FailureReason(HANDSHAKE_TIMEOUT)
    return FailureReason(UNKNOWN, name)


def parse_legacy(value: str | None) -> FailureReason | None:
    """Read error strings written before structured reasons existed."""
    if not value:
        return None
    category, _, detail = value.partition(":")
    if category in CATEGORIES:
        return FailureReason(category, detail)
    lowered = value.lower()
    if "timeout" in lowered:
        return FailureReason(CONNECT_TIMEOUT)
    if "refused" in lowered:
        return FailureReason(CONNECT_REFUSED)
    if "reset" in lowered:
        return FailureReason(CONNECT_RESET)
    if "ssl" in lowered or "tls" in lowered:
        return FailureReason(TLS_ERROR)
    return FailureReason(UNKNOWN, redact(value, 60))
