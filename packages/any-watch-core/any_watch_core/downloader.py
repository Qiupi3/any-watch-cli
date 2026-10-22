from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from .config import get_config

if TYPE_CHECKING:
    from .base import StreamInfo


def sanitize_filename(name: str) -> str:
    """Sanitize title for cross-platform filesystem compatibility."""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip().replace(" ", "_")


def download_stream(
    stream: StreamInfo, custom_dir: Path | None = None, category: str = "downloads"
) -> Path:
    """Download video stream with subtitles using yt-dlp."""
    cfg = get_config()
    out_dir = custom_dir or Path(cfg.download_dir) / category
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_name = sanitize_filename(stream.title)
    video_path = out_dir / f"{safe_name}.mp4"

    args = [
        "yt-dlp",
        stream.url,
        "--no-skip-unavailable-fragments",
        "--fragment-retries",
        "infinite",
        "-N",
        "16",
        "-o",
        str(video_path),
    ]
    if stream.referer:
        args.extend(["--referer", stream.referer])

    print(f"\n[+] Starting download for '{stream.title}' via yt-dlp...")
    proc = subprocess.Popen(args)
    proc.wait()

    # Download subtitle file if available
    if stream.subtitles:
        sub_url = stream.subtitles[0]
        sub_path = out_dir / f"{safe_name}.vtt"
        try:
            with httpx.Client(timeout=15, follow_redirects=True) as client:
                resp = client.get(sub_url)
                if resp.status_code == 200:
                    with open(sub_path, "wb") as f:
                        f.write(resp.content)
                    print(f"[+] Subtitles saved: {sub_path}")
        except Exception as e:
            print(f"[!] Warning: Subtitle download failed: {e}")

    print(f"[+] Download complete: {video_path}")
    return video_path
