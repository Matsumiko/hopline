from __future__ import annotations

import os
import stat
import tomllib
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class HoplineConfig:
    database: str
    subscriptions: tuple[str, ...]
    interval: float = 45 * 60
    jitter: float = 0

    @classmethod
    def from_file(cls, path: str | Path) -> "HoplineConfig":
        config_path = Path(path)
        if not config_path.is_file():
            raise ValueError(f"config file does not exist: {config_path}")
        mode = stat.S_IMODE(config_path.stat().st_mode)
        if mode & 0o077:
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
        if not urls:
            raise ValueError("at least one subscription URL is required")
        if interval <= 0 or jitter < 0 or jitter >= interval:
            raise ValueError("interval and jitter are invalid")
        return cls(database=database, subscriptions=tuple(urls), interval=interval, jitter=jitter)

    @classmethod
    def from_environment(cls) -> "HoplineConfig":
        path = os.environ.get("HOPLINE_CONFIG", "hopline.toml")
        return cls.from_file(path)
