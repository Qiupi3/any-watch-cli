from __future__ import annotations

import os
import platform as plt
import re
import shutil
import subprocess
import urllib.request
from typing import TYPE_CHECKING

from .config import get_config
from .proxy import StreamProxy, srt_to_vtt

if TYPE_CHECKING:
    from .base import StreamInfo, SubtitleTrack

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def is_android() -> bool:
    """Detect if running under Android (Termux)"""
    if "TERMUX_VERSION" in os.environ or "ANDROID_ROOT" in os.environ:
        return True
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

    # 2. Fallback to English if preferred was Indonesian but not available
    if pref in ("ind", "id", "indonesian", "indo"):
        for s in subtitles:
            if hasattr(s, "lang") and any(k in s.lang.lower() for k in ("eng", "en")):
                return s.url
            if hasattr(s, "label") and "english" in s.label.lower():
                return s.url
            if isinstance(s, str) and any(k in s.lower() for k in ("eng", "en.", "english")):
                return s

    # 3. Fallback to first available
    first = subtitles[0]
    return first.url if hasattr(first, "url") else first


def prepare_android_sub(sub_url: str | None, referer: str | None = None) -> str | None:
    """Download subtitle to /sdcard with Referer/UA and convert to WebVTT for local Android player reading."""
    if not sub_url:
        return None

    for base in ["/sdcard", "/storage/emulated/0"]:
        if os.path.exists(base):
            target = os.path.join(base, "any-watch-sub.vtt")
            try:
                req = urllib.request.Request(sub_url)
                req.add_header("User-Agent", USER_AGENT)
                if referer:
                    req.add_header("Referer", referer)
                with urllib.request.urlopen(req, timeout=12) as resp:
                    raw_content = resp.read().decode("utf-8", errors="replace")
                with open(target, "w", encoding="utf-8") as f:
                    f.write(srt_to_vtt(raw_content))
                return target
            except Exception:
                return None
    return None


def setup_mpv_android_conf(
    title: str,
    referer: str | None = None,
    local_sub_path: str | None = None,
    slang_val: str = "ind,id,eng,en",
    quality_fmt: str | None = None,
) -> None:
    """Write playback session settings directly into /sdcard/mpv/mpv.conf for is.xyz.mpv."""
    for base in ["/sdcard/mpv", "/storage/emulated/0/mpv"]:
        try:
            os.makedirs(base, exist_ok=True)
            conf_path = os.path.join(base, "mpv.conf")
            lines = [
                "# any-watch session configuration",
                "hwdec=auto",
                f"force-media-title=Playing {title}",
                f"slang={slang_val}",
            ]
            if referer:
                lines.append(f"referrer={referer}")
                lines.append(f"http-header-fields=Referer: {referer}")
            if local_sub_path:
                lines.append(f"sub-file={local_sub_path}")
            if quality_fmt:
                lines.append(f"ytdl-format={quality_fmt}")

            with open(conf_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            return
        except Exception:
            continue


def setup_vlc_android_m3u(stream_url: str, referer: str | None = None) -> str | None:
    """Create a temporary M3U playlist file with EXTVLCOPT for VLC if Referer is required."""
    if not referer:
        return None
    for base in ["/sdcard", "/storage/emulated/0"]:
        if os.path.exists(base):
            target = os.path.join(base, "any-watch-stream.m3u8")
            try:
                content = (
                    "#EXTM3U\n"
                    f"#EXTVLCOPT:http-referrer={referer}\n"
                    f"#EXTVLCOPT:http-user-agent={USER_AGENT}\n"
                    f"{stream_url}\n"
                )
                with open(target, "w", encoding="utf-8") as f:
                    f.write(content)
                return f"file://{target}"
            except Exception:
                return None
    return None


def play_stream(
    stream: StreamInfo,
    custom_player: str | None = None,
    sub_lang: str | None = None,
) -> None:
    """Launch player for the given stream on macOS, Linux, Windows, or Termux (Android)."""
    cfg = get_config()
    chosen_player = (custom_player or cfg.player or "mpv").lower().strip()
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
    quality_fmt: str | None = None
    mpv_quality_args: list[str] = []
    iina_quality_args: list[str] = []
    if chosen_quality and chosen_quality != "auto":
        m = re.search(r"(\d+)", chosen_quality)
        if m:
            h = m.group(1)
            quality_fmt = f"bestvideo[height<={h}]+bestaudio/best[height<={h}]/best"
            mpv_quality_args = [f"--ytdl-format={quality_fmt}"]
            iina_quality_args = [f"--mpv-ytdl-format={quality_fmt}"]

    # -----------------------------------------------------------------------
    # Android (Termux) Playback via Android Intent
    # -----------------------------------------------------------------------
    if is_android():
        player_type = chosen_player
        if player_type not in ("mpv", "vlc") and "/" not in player_type and "." not in player_type:
            player_type = "mpv"

        if player_type == "vlc":
            component = "org.videolan.vlc/org.videolan.vlc.gui.video.VideoPlayerActivity"
            player_name = "VLC"
        elif player_type == "mpv":
            component = "is.xyz.mpv/.MPVActivity"
            player_name = "MPV"
        else:
            component = player_type
            player_name = player_type

        # Download preferred subtitle locally to avoid 403 / CORS in Android players
        local_sub = prepare_android_sub(chosen_sub_url, referer=referer)
        sub_to_use = local_sub or chosen_sub_url

        print(f"\n[~] Android (Termux) Detected: Launching {player_name} Intent for '{title}' ~")

        if player_type == "mpv":
            # MPV on Android reads /sdcard/mpv/mpv.conf for session options (referer, sub-file, slang)
            setup_mpv_android_conf(
                title=title,
                referer=referer,
                local_sub_path=local_sub,
                slang_val=slang_val,
                quality_fmt=quality_fmt,
            )
            args = [
                "am",
                "start",
                "--user",
                "0",
                "-a",
                "android.intent.action.VIEW",
                "-d",
                url,
                "-t",
                "video/*",
                "-n",
                component,
                "-e",
                "title",
                f"Playing {title}",
            ]
        else:  # VLC
            vlc_play_url = setup_vlc_android_m3u(url, referer=referer) or url
            args = [
                "am",
                "start",
                "--user",
                "0",
                "-a",
                "android.intent.action.VIEW",
                "-d",
                vlc_play_url,
                "-t",
                "application/vnd.apple.mpegurl" if ".m3u" in vlc_play_url else "video/*",
                "-n",
                component,
                "-e",
                "title",
                f"Playing {title}",
            ]
            if sub_to_use:
                vlc_sub_uri = f"file://{sub_to_use}" if sub_to_use.startswith("/") else sub_to_use
                args.extend(["--es", "subtitles_location", vlc_sub_uri])

        try:
            res = subprocess.run(args, capture_output=True, text=True)
            if res.returncode == 0 and "Error:" not in res.stderr and "Error:" not in res.stdout:
                print(f"[+] Stream opened in {player_name}.")
                return
            else:
                err = (res.stderr or res.stdout).strip()
                print(f"[!] {player_name} intent launch failed: {err}")
        except Exception as e:
            print(f"[!] Error launching {player_name}: {e}")

        # Fallback to alternate player if primary failed
        if player_type == "mpv":
            fallback_comp = "org.videolan.vlc/org.videolan.vlc.gui.video.VideoPlayerActivity"
            fallback_name = "VLC"
            fb_play_url = setup_vlc_android_m3u(url, referer=referer) or url
            fb_args = [
                "am",
                "start",
                "--user",
                "0",
                "-a",
                "android.intent.action.VIEW",
                "-d",
                fb_play_url,
                "-t",
                "application/vnd.apple.mpegurl" if ".m3u" in fb_play_url else "video/*",
                "-n",
                fallback_comp,
                "-e",
                "title",
                f"Playing {title}",
            ]
            if sub_to_use:
                vlc_sub_uri = f"file://{sub_to_use}" if sub_to_use.startswith("/") else sub_to_use
                fb_args.extend(["--es", "subtitles_location", vlc_sub_uri])
        elif player_type == "vlc":
            fallback_comp = "is.xyz.mpv/.MPVActivity"
            fallback_name = "MPV"
            setup_mpv_android_conf(
                title=title,
                referer=referer,
                local_sub_path=local_sub,
                slang_val=slang_val,
                quality_fmt=quality_fmt,
            )
            fb_args = [
                "am",
                "start",
                "--user",
                "0",
                "-a",
                "android.intent.action.VIEW",
                "-d",
                url,
                "-t",
                "video/*",
                "-n",
                fallback_comp,
                "-e",
                "title",
                f"Playing {title}",
            ]
        else:
            fb_args = None

        if fb_args:
            print(f"[~] Attempting fallback to {fallback_name}...")
            try:
                fb_res = subprocess.run(fb_args, capture_output=True, text=True)
                if fb_res.returncode == 0 and "Error:" not in fb_res.stderr and "Error:" not in fb_res.stdout:
                    print(f"[+] Stream opened in {fallback_name}.")
                    return
            except Exception:
                pass

        if shutil.which("termux-open-url"):
            subprocess.run(["termux-open-url", url], check=False)
            return

        try:
            subprocess.run(
                ["am", "start", "--user", "0", "-a", "android.intent.action.VIEW", "-d", url],
                check=False,
            )
            return
        except Exception:
            pass

        return

    # -----------------------------------------------------------------------
    # macOS Playback
    # -----------------------------------------------------------------------
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
        elif chosen_player == "vlc" and shutil.which("vlc"):
            args = ["vlc", url, f"--meta-title=Playing {title}"]
            if referer:
                args.append(f":http-referrer={referer}")
            if chosen_sub_url:
                args.append(f"--sub-file={chosen_sub_url}")
            subprocess.run(args, check=False)
            return
        elif chosen_player == "mpv" and shutil.which("mpv"):
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

        # Fallbacks for macOS
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

        if shutil.which("iina"):
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

        if shutil.which("vlc"):
            args = ["vlc", url, f"--meta-title=Playing {title}"]
            if referer:
                args.append(f":http-referrer={referer}")
            if chosen_sub_url:
                args.append(f"--sub-file={chosen_sub_url}")
            subprocess.run(args, check=False)
            return

    # -----------------------------------------------------------------------
    # Linux / Windows / BSD
    # -----------------------------------------------------------------------
    if chosen_player == "vlc" and shutil.which("vlc"):
        args = ["vlc", url, f"--meta-title=Playing {title}"]
        if referer:
            args.append(f":http-referrer={referer}")
        if chosen_sub_url:
            args.append(f"--sub-file={chosen_sub_url}")
        subprocess.run(args, check=False)
        return
    elif (chosen_player == "mpv" or chosen_player not in ("vlc", "iina")) and shutil.which(chosen_player):
        args = [
            chosen_player,
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

    # Fallback to vlc if available
    if shutil.which("vlc"):
        args = ["vlc", url, f"--meta-title=Playing {title}"]
        if referer:
            args.append(f":http-referrer={referer}")
        if chosen_sub_url:
            args.append(f"--sub-file={chosen_sub_url}")
        subprocess.run(args, check=False)
        return

    print("\n[!] No supported video player found. Please install mpv, iina, or vlc.")
    print(f"[!] Direct Stream URL: {url}")
    if sub_urls:
        print("[!] Subtitles available:")
        for s in sub_urls:
            print(f"    - {s}")
