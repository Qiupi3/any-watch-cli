from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Config:
    player: str = "mpv"  # mpv, iina, vlc
    quality: str = "auto"
    sub_language: str = "ind"  # ind (Indonesian) or eng (English)
    stream_provider: str = "auto"


def _get_config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "any-watch"
    return Path.home() / ".config" / "any-watch"


CONFIG_DIR = _get_config_dir()
CONFIG_FILE = CONFIG_DIR / "config.json"


def get_config() -> Config:
    """Load configuration from disk, creating default if not found."""
    if not CONFIG_FILE.exists():
        cfg = Config()
        save_config(cfg)
        return cfg

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return Config(**data)
    except Exception:
        return Config()


def save_config(cfg: Config) -> None:
    """Save configuration to disk."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(cfg), f, indent=2)
    except Exception:
        pass
