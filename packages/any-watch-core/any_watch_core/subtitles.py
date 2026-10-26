from __future__ import annotations

"""Download and unpack subtitle files (SubDL and future subtitle providers)."""

import io
import re
import zipfile
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx

from .base import SubtitleResult
from .config import get_config
from .extract import DEFAULT_HEADERS


def _safe_name(value: str, fallback: str) -> str:
    value = re.sub(r"[^\w\s.-]", "", value or "").strip()
    value = re.sub(r"\s+", ".", value)
    return value[:120] or fallback


def _default_download_dir() -> Path:
    cfg = get_config()
    if cfg.download_dir:
        return Path(cfg.download_dir).expanduser()
    downloads = Path.home() / "Downloads"
    base = downloads if downloads.is_dir() else Path.cwd()
    return base / "any-watch-subtitles"


async def download_subtitle(
    result: SubtitleResult, dest_dir: Optional[Path] = None
) -> Path:
    """Download a subtitle result, extracting the first .srt/.vtt from a zip."""
    target_dir = Path(dest_dir) if dest_dir else _default_download_dir()
    target_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(
        headers=DEFAULT_HEADERS, timeout=30, follow_redirects=True
    ) as client:
        response = await client.get(result.url)
        response.raise_for_status()
        payload = response.content

    url_name = Path(urlparse(result.url).path).name
    base_name = _safe_name(
        f"{result.title}-{result.release}".strip("-"), "subtitle"
    )
    ext = Path(url_name).suffix.lower()

    if ext == ".zip" or payload[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            candidates = [
                name
                for name in archive.namelist()
                if name.lower().endswith((".srt", ".vtt", ".ass", ".ssa"))
            ]
            if not candidates:
                raise RuntimeError("Subtitle archive did not contain a subtitle file.")
            chosen = next(
                (n for n in candidates if "ind" in n.lower() or n.lower().endswith(".srt")),
                candidates[0],
            )
            data = archive.read(chosen)
            suffix = Path(chosen).suffix.lower()
    else:
        data = payload
        suffix = ext if ext in (".srt", ".vtt", ".ass", ".ssa") else ".srt"

    destination = target_dir / f"{base_name}{suffix}"
    destination.write_bytes(data)
    return destination
