from __future__ import annotations

import ipaddress
import json
import re
import time
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass


DEFAULT_EXIT_IP_URL = "https://api.ipify.org?format=json"


@dataclass(frozen=True, slots=True)
class GeoResult:
    ip: str
    country_code: str
    country: str | None
    asn: str | None
    organization: str | None
    provider: str
    checked_at: float


class GeoLookupError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GeoProvider:
    name: str
    url: Callable[[str], str]
    parse: Callable[[dict], tuple[str, str, str | None, str | None, str | None]]
    headers: tuple[tuple[str, str], ...] = ()


class GeolocationResolver:
    """Resolve an observed exit IP with ordered, replaceable providers."""

    def __init__(
        self,
        providers: Iterable[GeoProvider] | None = None,
        *,
        fetch: Callable[[str, tuple[tuple[str, str], ...]], dict] | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.providers = tuple(providers or default_providers())
        self.fetch = fetch or _fetch_json
        self.clock = clock
        if not self.providers:
            raise ValueError("at least one geolocation provider is required")

    def resolve(self, ip: str) -> GeoResult:
        _require_ip(ip)
        errors: list[str] = []
        for provider in self.providers:
            try:
                payload = self.fetch(provider.url(ip), provider.headers)
                observed_ip, country_code, country, asn, organization = provider.parse(payload)
                if observed_ip != ip:
                    raise GeoLookupError("provider returned a different IP")
                return GeoResult(ip, country_code, country, asn, organization, provider.name, self.clock())
            except (KeyError, TypeError, ValueError, GeoLookupError, OSError, json.JSONDecodeError) as error:
                errors.append(f"{provider.name}:{type(error).__name__}")
        raise GeoLookupError("all geolocation providers failed: " + ", ".join(errors))


def fetch_exit_ip(
    *,
    proxy_host: str,
    proxy_port: int,
    proxy_username: str,
    proxy_password: str,
    target_url: str = DEFAULT_EXIT_IP_URL,
    timeout: float = 10,
    fetch: Callable[[str, str, float], bytes] | None = None,
) -> str:
    """Fetch the observed public IP through one Hopline node route."""
    parsed = urllib.parse.urlsplit(target_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("exit IP URL must be an HTTPS URL without credentials or fragments")
    if not proxy_host or not 1 <= proxy_port <= 65535:
        raise ValueError("exit IP proxy endpoint is invalid")
    if not proxy_username or not proxy_password or timeout <= 0:
        raise ValueError("exit IP proxy credentials or timeout are invalid")
    proxy_url = "http://" + urllib.parse.quote(proxy_username, safe="") + ":" + urllib.parse.quote(proxy_password, safe="") + "@" + proxy_host + ":" + str(proxy_port)
    body = fetch(target_url, proxy_url, timeout) if fetch is not None else _fetch_through_proxy(target_url, proxy_url, timeout)
    try:
        payload = json.loads(body)
        value = payload.get("ip") if isinstance(payload, dict) else None
    except json.JSONDecodeError:
        value = body.decode("utf-8").strip()
    _require_ip(value)
    return value


def is_fresh(result: GeoResult, *, now: float, max_age: float) -> bool:
    if max_age <= 0:
        raise ValueError("geolocation max_age must be positive")
    return 0 <= now - result.checked_at <= max_age


def default_providers() -> tuple[GeoProvider, ...]:
    return (
        GeoProvider(
            "checkip",
            lambda ip: "https://checkip.com/api/v1/ip?" + urllib.parse.urlencode({"ip": ip}),
            _parse_checkip,
        ),
        GeoProvider(
            "ipcc",
            lambda ip: "https://ip.cc/webapi/product/api-ip-address?" + urllib.parse.urlencode({"language": "en", "ip": ip}),
            _parse_ipcc,
        ),
        GeoProvider(
            "cekipsaya",
            lambda ip: "https://cekipsaya.com/api/?" + urllib.parse.urlencode({"action": "lookup", "target": ip}),
            _parse_cekipsaya,
            (("Referer", "https://cekipsaya.com/cek-ip-saya/"),),
        ),
    )


def _fetch_through_proxy(target_url: str, proxy_url: str, timeout: float) -> bytes:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
    request = urllib.request.Request(target_url, headers={"Accept": "application/json"}, method="GET")
    try:
        with opener.open(request, timeout=timeout) as response:
            return response.read(16 * 1024)
    except OSError as error:
        raise GeoLookupError("exit IP request failed") from error


def _fetch_json(url: str, headers: tuple[tuple[str, str], ...]) -> dict:
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    with urllib.request.urlopen(request, timeout=5) as response:
        payload = json.loads(response.read(128 * 1024))
    if not isinstance(payload, dict):
        raise GeoLookupError("geolocation response is not an object")
    return payload


def _parse_checkip(payload: dict) -> tuple[str, str, str | None, str | None, str | None]:
    if payload.get("code") != "OK" or not isinstance(payload.get("data"), dict):
        raise GeoLookupError("checkip response is unsuccessful")
    data = payload["data"]
    _require_ip(data.get("ip"))
    return data["ip"], _require_code(data.get("country_code")), data.get("ip_location"), data.get("asn"), data.get("organization")


def _parse_ipcc(payload: dict) -> tuple[str, str, str | None, str | None, str | None]:
    if payload.get("code") != 200 or not isinstance(payload.get("data"), dict):
        raise GeoLookupError("ip.cc response is unsuccessful")
    geo = payload["data"].get("geolocation")
    asn_data = payload["data"].get("asn")
    if not isinstance(geo, dict):
        raise GeoLookupError("ip.cc geolocation is missing")
    _require_ip(geo.get("ip"))
    asn = asn_data.get("asn") if isinstance(asn_data, dict) else None
    return geo["ip"], _require_code(geo.get("country_code")), geo.get("country"), asn, geo.get("organization")


def _parse_cekipsaya(payload: dict) -> tuple[str, str, str | None, str | None, str | None]:
    _require_ip(payload.get("ip"))
    country = payload.get("country")
    match = re.search(r"\(([A-Za-z]{2})\)", country or "")
    return payload["ip"], _require_code(match.group(1) if match else None), country, payload.get("asn"), payload.get("org")


def _require_ip(value: object) -> None:
    if not isinstance(value, str):
        raise GeoLookupError("geolocation IP is missing or invalid")
    try:
        ipaddress.ip_address(value)
    except ValueError as error:
        raise GeoLookupError("geolocation IP is missing or invalid") from error


def _require_code(value: object) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z]{2}", value):
        raise GeoLookupError("geolocation country code is missing or invalid")
    return value.upper()
