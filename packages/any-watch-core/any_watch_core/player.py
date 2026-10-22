from __future__ import annotations

import platform as plt
import shutil
import subprocess
from typing import TYPE_CHECKING

from .config import get_config

if TYPE_CHECKING:
    from .base import StreamInfo


def is_android() -> bool:
    """Detect if running under Android (Termux)"""
    try:
        cmd = subprocess.check_output(["uname", "-o"], stderr=subprocess.DEVNULL)
        return cmd.decode("utf-8").strip() == "Android"
    except Exception:
        return False


def play_stream(stream: StreamInfo, custom_player: str | None = None) -> None:
    """Launch player for the given stream on macOS, Linux, Windows, or Termux (Android)."""
    cfg = get_config()
    chosen_player = custom_player or cfg.player or "mpv"
    system = plt.system()

    url = stream.url
    title = stream.title
    referer = stream.referer
    subtitles = stream.subtitles

    if is_android():
        print("~ Android (Termux) Detected: Launching VLC Intent ~")
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
        if subtitles:
            args.extend(["--es", "subtitles_location", subtitles[0]])

        try:
            subprocess.run(args, check=True, capture_output=True)
            print("~ Stream opened in VLC ~")
            return
        except Exception:
            # Fallback to termux-open
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
            ]
            if referer:
                args.append(f"--mpv-referrer={referer}")
            args.extend(f"--mpv-sub-files={s}" for s in subtitles)
            proc = subprocess.Popen(args, stdout=subprocess.DEVNULL)
            proc.wait()
            return

        # If chosen is mpv or iina was not found
        if shutil.which("mpv"):
            args = [
                "mpv",
                url,
                f"--force-media-title=Playing {title}",
            ]
            if referer:
                args.append(f"--referrer={referer}")
            args.extend(f"--sub-file={s}" for s in subtitles)
            proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc.wait()
            return

        if shutil.which("vlc"):
            args = ["vlc", url, f"--meta-title=Playing {title}"]
            if subtitles:
                args.append(f"--sub-file={subtitles[0]}")
            subprocess.run(args, check=False)
            return

    # Linux, Windows, FreeBSD
    if shutil.which(chosen_player):
        if chosen_player == "mpv":
            args = [
                "mpv",
                url,
                f"--force-media-title=Playing {title}",
            ]
            if referer:
                args.append(f"--referrer={referer}")
            args.extend(f"--sub-file={s}" for s in subtitles)
            proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc.wait()
            return
        elif chosen_player == "vlc":
            args = ["vlc", url, f"--meta-title=Playing {title}"]
            if subtitles:
                args.append(f"--sub-file={subtitles[0]}")
            subprocess.run(args, check=False)
            return

    # Fallback to mpv if available
    if shutil.which("mpv"):
        args = ["mpv", url, f"--force-media-title=Playing {title}"]
        if referer:
            args.append(f"--referrer={referer}")
        args.extend(f"--sub-file={s}" for s in subtitles)
        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proc.wait()
        return

    print("\n[!] No supported video player found. Please install mpv, iina, or vlc.")
    print(f"[!] Direct Stream URL: {url}")
    if subtitles:
        print(f"[!] Subtitle URL: {subtitles[0]}")
