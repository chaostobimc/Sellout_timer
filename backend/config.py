from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Config:
    raw: dict[str, Any]
    base_dir: Path

    @property
    def server(self) -> dict[str, Any]: return self.raw.get("server", {})
    @property
    def multipliers(self) -> dict[str, float]: return self.raw.get("multipliers", {})
    @property
    def minecraft(self) -> dict[str, Any]: return self.raw.get("minecraft", {})
    @property
    def twitch(self) -> dict[str, Any]: return self.raw.get("twitch", {})
    @property
    def discord(self) -> dict[str, Any]: return self.raw.get("discord", {})
    @property
    def timer(self) -> dict[str, Any]: return self.raw.get("timer", {})

    def resolve_path(self, value: str | os.PathLike[str]) -> Path:
        path = Path(value).expanduser().resolve()
        if not path.is_absolute(): path = self.base_dir / path
        return path


def load_config(path: str | os.PathLike[str] = "config.json") -> Config:
    config_path = Path(path).expanduser().resolve()
    env_path = config_path.parent / ".env"
    try:
        from dotenv import load_dotenv
        if env_path.exists(): load_dotenv(env_path, override=True)
        else: load_dotenv(override=True)
    except ImportError:
        log.warning("python-dotenv nicht installiert")
    with open(config_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    log.info("Config geladen: %s", config_path)
    return Config(raw=raw, base_dir=config_path.parent)
