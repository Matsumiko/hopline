from __future__ import annotations

import stat
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class HoplineConfig:
    database: str
    subscriptions: tuple[str, ...]
    static_nodes: tuple[str, ...] = ()
    interval: float = 45 * 60
    jitter: float = 0
    gateway_host: str = "127.0.0.1"
    gateway_port: int = 18770
    tunnel_port: int = 18771
    control_port: int = 18772
    country_max_age: float = 60 * 60
    capability_enabled: bool = False
    capability_max_age: float = 60 * 60
    capability_interval: float = 15 * 60
    capability_timeout: float = 20
    capability_concurrency: int = 1
    capability_ipv4_url: str = "https://api4.ipify.org?format=json"
    capability_ipv6_url: str = "https://api6.ipify.org?format=json"
    sing_box_binary: str = "sing-box"
    engine_workdir: str = ""
    max_active_connections: int = 64
    probe_targets: tuple[str, ...] = ()
    probe_concurrency: int = 10
    probe_interval: float = 5 * 60
    probe_timeout: float = 5
    probe_mode: str = "tcp"
    probe_proxy_host: str = "127.0.0.1"
    probe_proxy_port: int = 18771
    metrics_enabled: bool = False
    metrics_host: str = "127.0.0.1"
    metrics_port: int = 18773
    proxy_username: str = field(default="hopline", repr=False)
    proxy_password: str = field(default="", repr=False)

    @classmethod
    def from_file(cls, path: str | Path) -> "HoplineConfig":
        config_path = Path(path)
        if not config_path.is_file():
            raise ValueError(f"config file does not exist: {config_path}")
        if stat.S_IMODE(config_path.stat().st_mode) & 0o077:
            raise ValueError("config file must not be readable by group or other users")
        try:
            document = tomllib.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise ValueError("config file is invalid") from exc
        section = document.get("hopline", {})
        if not isinstance(section, dict):
            raise ValueError("[hopline] section is required")
        database = str(section.get("database", "hopline.db"))
        interval = float(section.get("interval", 45 * 60))
        jitter = float(section.get("jitter", 0))
        gateway_host = str(section.get("gateway_host", "127.0.0.1"))
        gateway_port = int(section.get("gateway_port", 18770))
        tunnel_port = int(section.get("tunnel_port", 18771))
        control_port = int(section.get("control_port", 18772))
        country_max_age = float(section.get("country_max_age", 60 * 60))
        sing_box_binary = str(section.get("sing_box_binary", "sing-box"))
        engine_workdir = str(section.get("engine_workdir", ""))
        max_active_connections = int(section.get("max_active_connections", 64))
        subscriptions = document.get("subscriptions", [])
        if not isinstance(subscriptions, list):
            raise ValueError("subscriptions must be an array of tables")
        urls: list[str] = []
        for item in subscriptions:
            if not isinstance(item, dict):
                raise ValueError("each subscription must be a table")
            url = str(item.get("url", ""))
            parsed = urlsplit(url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("subscription URL must be an HTTP(S) URL")
            urls.append(url)
        static_entries = document.get("static_nodes", [])
        if not isinstance(static_entries, list):
            raise ValueError("static_nodes must be an array")
        static_nodes: list[str] = []
        for entry in static_entries:
            node = str(entry)
            parsed = urlsplit(node)
            if parsed.scheme not in {"vless", "vmess", "trojan", "ss"} or not parsed.hostname:
                raise ValueError("static node must be a supported share link")
            static_nodes.append(node)
        if not urls and not static_nodes:
            raise ValueError("at least one subscription URL or static node is required")

        health = document.get("health", {})
        if not isinstance(health, dict):
            raise ValueError("[health] section must be a table")
        raw_targets = health.get("targets", [])
        if not isinstance(raw_targets, list):
            raise ValueError("health.targets must be an array")
        targets: list[str] = []
        for raw_target in raw_targets:
            target = str(raw_target)
            parsed_target = urlsplit(target)
            if parsed_target.scheme not in {"http", "https"} or not parsed_target.hostname:
                raise ValueError("health probe target must be an HTTP(S) URL")
            if parsed_target.username or parsed_target.password or parsed_target.fragment:
                raise ValueError("health probe target must not contain credentials or fragments")
            targets.append(target)
        probe_interval = float(health.get("interval", 5 * 60))
        probe_timeout = float(health.get("timeout", 5))
        probe_concurrency = int(health.get("concurrency", 10))
        probe_mode = str(health.get("mode", "tcp"))
        if probe_mode not in {"tcp", "http"}:
            raise ValueError("health.mode must be tcp or http")
        probe_proxy_host = str(health.get("proxy_host", "127.0.0.1"))
        probe_proxy_port = int(health.get("proxy_port", tunnel_port))
        metrics_enabled = bool(health.get("metrics_enabled", False))
        metrics_host = str(health.get("metrics_host", "127.0.0.1"))
        metrics_port = int(health.get("metrics_port", 18773))
        capability = document.get("capability", {})
        if not isinstance(capability, dict):
            raise ValueError("[capability] section must be a table")
        capability_enabled = bool(capability.get("enabled", False))
        capability_max_age = float(capability.get("max_age", 60 * 60))
        capability_interval = float(capability.get("interval", 15 * 60))
        capability_timeout = float(capability.get("timeout", 20))
        capability_concurrency = int(capability.get("concurrency", 1))
        capability_ipv4_url = str(capability.get("ipv4_url", "https://api4.ipify.org?format=json"))
        capability_ipv6_url = str(capability.get("ipv6_url", "https://api6.ipify.org?format=json"))
        for capability_url in (capability_ipv4_url, capability_ipv6_url):
            parsed_capability_url = urlsplit(capability_url)
            if parsed_capability_url.scheme != "https" or not parsed_capability_url.hostname:
                raise ValueError("capability target must be an HTTPS URL")
            if parsed_capability_url.username or parsed_capability_url.password or parsed_capability_url.fragment:
                raise ValueError("capability target must not contain credentials or fragments")
        auth = document.get("auth", {})
        if not isinstance(auth, dict):
            raise ValueError("[auth] section must be a table")
        proxy_username = auth.get("username", "hopline")
        proxy_password = auth.get("password")
        if not isinstance(proxy_username, str) or not proxy_username:
            raise ValueError("auth.username must be a non-empty string")
        if not isinstance(proxy_password, str) or not proxy_password:
            raise ValueError("auth.password must be a non-empty string")

        if interval <= 0 or jitter < 0 or jitter >= interval:
            raise ValueError("interval and jitter are invalid")
        if gateway_host not in {"127.0.0.1", "::1", "localhost"} or not 0 <= gateway_port <= 65535:
            raise ValueError("gateway endpoint is invalid")
        if not 1 <= tunnel_port <= 65535 or gateway_port == tunnel_port:
            raise ValueError("tunnel endpoint is invalid")
        if not 0 <= control_port <= 65535 or control_port in {gateway_port, tunnel_port}:
            raise ValueError("control endpoint is invalid")
        if not sing_box_binary or max_active_connections <= 0:
            raise ValueError("sing-box runtime settings are invalid")
        if capability_max_age <= 0 or capability_interval <= 0 or capability_timeout <= 0 or capability_timeout > capability_interval or capability_concurrency <= 0:
            raise ValueError("capability settings are invalid")
        if not probe_proxy_host or not 1 <= probe_proxy_port <= 65535:
            raise ValueError("health proxy endpoint is invalid")
        if metrics_host not in {"127.0.0.1", "::1", "localhost"} or not 1 <= metrics_port <= 65535:
            raise ValueError("health metrics endpoint is invalid")
        return cls(
            database=database,
            subscriptions=tuple(urls),
            static_nodes=tuple(static_nodes),
            interval=interval,
            jitter=jitter,
            gateway_host=gateway_host,
            gateway_port=gateway_port,
            tunnel_port=tunnel_port,
            control_port=control_port,
            country_max_age=country_max_age,
            capability_enabled=capability_enabled,
            capability_max_age=capability_max_age,
            capability_interval=capability_interval,
            capability_timeout=capability_timeout,
            capability_concurrency=capability_concurrency,
            capability_ipv4_url=capability_ipv4_url,
            capability_ipv6_url=capability_ipv6_url,
            sing_box_binary=sing_box_binary,
            probe_targets=tuple(targets),
            probe_interval=probe_interval,
            probe_timeout=probe_timeout,
            probe_concurrency=probe_concurrency,
            probe_mode=probe_mode,
            probe_proxy_host=probe_proxy_host,
            probe_proxy_port=probe_proxy_port,
            metrics_enabled=metrics_enabled,
            metrics_host=metrics_host,
            metrics_port=metrics_port,
            proxy_username=proxy_username,
            proxy_password=proxy_password,
        )
    @classmethod
    def from_environment(cls) -> "HoplineConfig":
        return cls.from_file(os.environ.get("HOPLINE_CONFIG", "hopline.toml"))
