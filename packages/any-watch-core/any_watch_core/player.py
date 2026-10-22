from __future__ import annotations

import platform as plt
import re
import shutil
import subprocess
from typing import TYPE_CHECKING

from .config import get_config

if TYPE_CHECKING:
    from .base import StreamInfo, SubtitleTrack


def is_android() -> bool:
    """Detect if running under Android (Termux)"""
    try:
        cmd = subprocess.check_output(["uname", "-o"], stderr=subprocess.DEVNULL)
        return cmd.decode("utf-8").strip() == "Android"
    except Exception:
        return False


def _get_sub_urls(subtitles: list[SubtitleTrack | str]) -> list[str]:
    """Helper to get pure URLs from subtitle list."""
    urls = []
    for s in subtitles:
        if hasattr(s, "url"):
            urls.append(s.url)
        elif isinstance(s, str):
            urls.append(s)
    return urls


def _pick_preferred_sub(subtitles: list[SubtitleTrack | str], preferred_lang: str) -> str | None:
    """Pick single best subtitle URL matching preferred language (e.g. for VLC/Termux)."""
    if not subtitles:
        return None

    pref = preferred_lang.lower()
    # 1. Match by lang code or label
    for s in subtitles:
        if hasattr(s, "lang") and pref in s.lang.lower():
            return s.url
        if hasattr(s, "label") and pref in s.label.lower():
            return s.url
        if isinstance(s, str) and (pref in s.lower() or ("ind" in pref and ("id." in s or "ind" in s))):
            return s

    # 2. Fallback to first available
    first = subtitles[0]
    return first.url if hasattr(first, "url") else first


def play_stream(
    stream: StreamInfo,
    custom_player: str | None = None,
    sub_lang: str | None = None,
) -> None:
    """Launch player for the given stream on macOS, Linux, Windows, or Termux (Android)."""
    cfg = get_config()
    chosen_player = custom_player or cfg.player or "mpv"
    preferred_lang = (sub_lang or cfg.sub_language or "ind").lower()
    system = plt.system()

    url = stream.url
    title = stream.title
    referer = stream.referer
    sub_urls = _get_sub_urls(stream.subtitles)

    # Determine subtitle language priority for MPV/IINA
    if preferred_lang in ("ind", "id", "indonesian", "indo"):
        slang_val = "ind,id,indonesian,indo,eng,en,english"
        chosen_sub_url = _pick_preferred_sub(stream.subtitles, "ind")
    else:
        slang_val = "eng,en,english,ind,id,indonesian,indo"
        chosen_sub_url = _pick_preferred_sub(stream.subtitles, "eng")

    # Determine quality cap for MPV / IINA
    chosen_quality = stream.quality or cfg.quality or "auto"
    mpv_quality_args: list[str] = []
    iina_quality_args: list[str] = []
    if chosen_quality and chosen_quality != "auto":
        m = re.search(r"(\d+)", chosen_quality)
        if m:
            h = m.group(1)
            fmt = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
            mpv_quality_args = [f"--ytdl-format={fmt}"]
            iina_quality_args = [f"--mpv-ytdl-format={fmt}"]

    # Android (Termux) Playback via VLC Intent
    if is_android():
        print(f"\n[~] Android (Termux) Detected: Launching VLC Intent for '{title}' ~")
        args = [
            "am",
            "start",
            "--user",
            "0",
            "-a",
            "android.intent.action.VIEW",
            "-d",
            url,
            "-n",
            "org.videolan.vlc/org.videolan.vlc.gui.video.VideoPlayerActivity",
            "-e",
            "title",
            f"Playing {title}",
        ]
        if chosen_sub_url:
            args.extend(["--es", "subtitles_location", chosen_sub_url])

        try:
            subprocess.run(args, check=True, capture_output=True)
            print("[+] Stream opened in VLC.")
            return
        except Exception:
            if shutil.which("termux-open-url"):
                subprocess.run(["termux-open-url", url], check=False)
                return

    # macOS Playback
    if system == "Darwin":
        if chosen_player == "iina" and shutil.which("iina"):
            args = [
                "iina",
                "--no-stdin",
                "--keep-running",
                url,
                f"--mpv-force-media-title=Playing {title}",
                f"--mpv-slang={slang_val}",
            ]
            args.extend(iina_quality_args)
            if referer:
                args.append(f"--mpv-referrer={referer}")
            for s_url in sub_urls:
                args.append(f"--mpv-sub-files={s_url}")

            proc = subprocess.Popen(args, stdout=subprocess.DEVNULL)
            proc.wait()
            return

        if shutil.which("mpv"):
            args = [
                "mpv",
                url,
                f"--force-media-title=Playing {title}",
                f"--slang={slang_val}",
            ]
            args.extend(mpv_quality_args)
            if referer:
                args.append(f"--referrer={referer}")
            for s_url in sub_urls:
                args.append(f"--sub-file={s_url}")

            proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc.wait()
            return

        if shutil.which("vlc"):
            args = ["vlc", url, f"--meta-title=Playing {title}"]
            if chosen_sub_url:
                args.append(f"--sub-file={chosen_sub_url}")
            subprocess.run(args, check=False)
            return

    # Linux / Windows / BSD
    if shutil.which(chosen_player):
        if chosen_player == "mpv":
            args = [
                "mpv",
                url,
                f"--force-media-title=Playing {title}",
                f"--slang={slang_val}",
            ]
            args.extend(mpv_quality_args)
            if referer:
                args.append(f"--referrer={referer}")
            for s_url in sub_urls:
                args.append(f"--sub-file={s_url}")

            proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc.wait()
            return
        elif chosen_player == "vlc":
            args = ["vlc", url, f"--meta-title=Playing {title}"]
            if chosen_sub_url:
                args.append(f"--sub-file={chosen_sub_url}")
            subprocess.run(args, check=False)
            return

    # Fallback to mpv if available
    if shutil.which("mpv"):
        args = [
            "mpv",
            url,
            f"--force-media-title=Playing {title}",
            f"--slang={slang_val}",
        ]
        if referer:
            args.append(f"--referrer={referer}")
        for s_url in sub_urls:
            args.append(f"--sub-file={s_url}")

        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proc.wait()
        return

    print("\n[!] No supported video player found. Please install mpv, iina, or vlc.")
    print(f"[!] Direct Stream URL: {url}")
    if sub_urls:
        print("[!] Subtitles available:")
        for s in sub_urls:
            print(f"    - {s}")
