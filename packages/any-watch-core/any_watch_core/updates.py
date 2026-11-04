"""Version checks, update reminders, and self-update helpers.

The CLI checks a small JSON manifest once per day (cached under
``~/.config/any-watch/update-check.json``) and reminds you when a newer
``MAJOR.CATEGORY.AREA.SITE`` version is published. Answering *yes* to the
prompt runs the matching installer (``uv tool`` preferred, ``pip`` otherwise).

Set ``ANY_WATCH_NO_UPDATE_CHECK=1`` or ``"check_updates": false`` in the config
to opt out, ``ANY_WATCH_UPDATE_URL`` to use another manifest, or
``ANY_WATCH_WHEEL_INDEX`` to install from a wheel directory / simple index.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

import httpx

from .config import CONFIG_DIR, get_config
from .version import __version__

DEFAULT_MANIFEST_URL = (
    "https://raw.githubusercontent.com/any-watch-cli/any-watch-cli/main/version.json"
)
CACHE_FILE = CONFIG_DIR / "update-check.json"
CACHE_TTL = 24 * 60 * 60  # seconds


@dataclass
class UpdateInfo:
    version: str
    url: str = ""
    notes: str = ""
    index_url: str = ""


def parse_version(value: str) -> tuple[int, int, int, int]:
    """Normalise ``1.1.0`` / ``v1.1.0.1`` / ``1.1.0.1-beta`` to four integers."""
    text = (value or "").strip().lstrip("vV")
    parts: list[int] = []
    for chunk in text.replace("-", ".").split("."):
        digits = "".join(ch for ch in chunk if ch.isdigit())
        parts.append(int(digits) if digits else 0)
        if len(parts) == 4:
            break
    while len(parts) < 4:
        parts.append(0)
    return parts[0], parts[1], parts[2], parts[3]


def is_newer(remote: str, local: str = __version__) -> bool:
    return parse_version(remote) > parse_version(local)


def _manifest_url() -> str:
    return (
        os.environ.get("ANY_WATCH_UPDATE_URL")
        or get_config().update_url
        or DEFAULT_MANIFEST_URL
    )


def _wheel_index() -> str:
    return os.environ.get("ANY_WATCH_WHEEL_INDEX", "") or get_config().wheel_index


def _parse_manifest(data: dict) -> Optional[UpdateInfo]:
    version = (
        data.get("version")
        or data.get("tag_name")
        or data.get("latest")
        or ""
    )
    if not version:
        return None
    notes = data.get("notes") or data.get("body") or data.get("changelog") or ""
    return UpdateInfo(
        version=str(version).strip().lstrip("vV"),
        url=data.get("url") or data.get("html_url") or "",
        notes=str(notes).strip().splitlines()[0] if notes else "",
        index_url=data.get("index_url") or _wheel_index(),
    )


def _read_cache() -> Optional[UpdateInfo]:
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        checked_at = float(data.get("checked_at", 0))
        if time.time() - checked_at > CACHE_TTL:
            return None
        version = data.get("latest") or ""
        if not version:
            return None
        return UpdateInfo(
            version=version,
            url=data.get("url", ""),
            notes=data.get("notes", ""),
            index_url=data.get("index_url", "") or _wheel_index(),
        )
    except Exception:
        return None


def _write_cache(info: UpdateInfo) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as fh:
            json.dump(
                {
                    "checked_at": time.time(),
                    "latest": info.version,
                    "url": info.url,
                    "notes": info.notes,
                    "index_url": info.index_url,
                },
                fh,
                indent=2,
            )
    except Exception:
        pass


def fetch_latest(timeout: float = 3.0) -> Optional[UpdateInfo]:
    """Fetch the published version manifest. Returns ``None`` on any failure."""
    try:
        response = httpx.get(
            _manifest_url(),
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": f"any-watch/{__version__}"},
        )
        if response.status_code != 200:
            return None
        return _parse_manifest(response.json())
    except Exception:
        return None


def check_for_update(
    force: bool = False,
    timeout: float = 2.5,
    allow_network: bool = True,
) -> Optional[UpdateInfo]:
    """Return update info when a newer version exists, otherwise ``None``."""
    info = None if force else _read_cache()
    if info is None:
        if not allow_network:
            return None
        info = fetch_latest(timeout=timeout)
        if info is None:
            return None
        _write_cache(info)
    if not info.version or not is_newer(info.version):
        return None
    return info


def reminder(info: UpdateInfo) -> str:
    note = f" — {info.notes}" if info.notes else ""
    return (
        f"[i] Update available: {__version__} → {info.version}{note}. "
        "Run `any-watch --update` to install it."
    )


def _installer_command(info: UpdateInfo) -> list[str]:
    target = f"any-watch>={info.version}"
    if shutil.which("uv"):
        cmd = ["uv", "tool", "install", "--force"]
        if info.index_url:
            cmd += ["--find-links", info.index_url]
        cmd.append(target)
        return cmd
    return [sys.executable, "-m", "pip", "install", "--upgrade", target]


def perform_update(info: UpdateInfo) -> bool:
    """Run the detected installer. Returns ``True`` on success."""
    cmd = _installer_command(info)
    print(f"\n[~] Updating any-watch to {info.version} ...")
    print(f"    {' '.join(cmd)}")
    try:
        result = subprocess.run(cmd, check=False)
    except Exception as exc:  # noqa: BLE001 - surface installer problems
        print(f"[!] Could not start the installer: {exc}")
        return False
    if result.returncode == 0:
        print(f"[+] Updated to {info.version}. Re-run the command you just used.")
        return True
    print("[!] Automatic update failed. Install the new wheels manually:")
    print(
        "    uv tool install --force --find-links ./release/ "
        "./release/any_watch-*.whl"
    )
    if info.url:
        print(f"    or open {info.url}")
    return False


def maybe_check(
    interactive: bool = True,
    allow_prompt: bool = True,
) -> Optional[UpdateInfo]:
    """Check (cached) and show/perform the update reminder. Never raises."""
    try:
        cfg = get_config()
        if not cfg.check_updates or os.environ.get("ANY_WATCH_NO_UPDATE_CHECK"):
            return None
        # Never add network latency to piped/scripted runs: use the cache only.
        info = check_for_update(allow_network=interactive)
        if not info:
            return None
        print()
        print(reminder(info))
        if interactive and allow_prompt and sys.stdin.isatty():
            try:
                answer = input("Update now? [Y/n] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                return info
            if answer in ("", "y", "yes"):
                perform_update(info)
        return info
    except Exception:
        return None
