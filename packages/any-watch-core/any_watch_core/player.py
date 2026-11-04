from __future__ import annotations

import os
import platform as plt
import re
import shutil
import subprocess
from typing import TYPE_CHECKING

from .config import get_config

if TYPE_CHECKING:
    from .base import StreamInfo, SubtitleTrack

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# Providers resolve direct media/HLS URLs themselves, so mpv's youtube-dl hook
# must stay out of the way: it re-requests the URL with its own user agent and
# turns working googlevideo/CDN links into 403s.
_DIRECT_MEDIA_RE = re.compile(
    r"\.(?:m3u8|mpd|mp4|m4v|webm|mkv|ts)(?:$|[?#])"
    r"|/videoplayback\?"
    r"|/api/hls\?",
    re.IGNORECASE,
)


def _looks_direct(url: str) -> bool:
    return bool(_DIRECT_MEDIA_RE.search(url))


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


def setup_mpv_android_conf(
    referer: str | None = None,
    sub_urls: list[str] | None = None,
    preferred_sub: str | None = None,
) -> None:
    """Mimic ani-cli: write referrer and sub-file into /storage/emulated/0/mpv/mpv.config.mp4 (and mpv.conf)."""
    lines: list[str] = []
    if referer:
        lines.append(f"referrer={referer}")
    if preferred_sub:
        lines.append(f"sub-file={preferred_sub}")
    if sub_urls:
        for s in sub_urls:
            if s and s != preferred_sub:
                lines.append(f"sub-file={s}")

    content = "\n".join(lines) + "\n" if lines else ""

    for conf_dir in ["/storage/emulated/0/mpv", "/sdcard/mpv"]:
        try:
            os.makedirs(conf_dir, exist_ok=True)
            for fname in ["mpv.config.mp4", "mpv.conf"]:
                target = os.path.join(conf_dir, fname)
                with open(target, "w", encoding="utf-8") as f:
                    f.write(content)
            return
        except Exception:
            continue


def _mpv_command(
    player: str,
    url: str,
    title: str,
    slang_val: str,
    quality_args: list[str],
    referer: str | None,
    sub_urls: list[str],
    user_agent: str,
) -> list[str]:
    args = [
        player,
        url,
        f"--force-media-title=Playing {title}",
        f"--slang={slang_val}",
        f"--user-agent={user_agent}",
    ]
    if _looks_direct(url):
        args.append("--ytdl=no")
    args.extend(quality_args)
    if referer:
        args.append(f"--referrer={referer}")
    for s_url in sub_urls:
        args.append(f"--sub-file={s_url}")
    return args


def _iina_command(
    url: str,
    title: str,
    slang_val: str,
    quality_args: list[str],
    referer: str | None,
    sub_urls: list[str],
    user_agent: str,
) -> list[str]:
    args = [
        "iina",
        "--no-stdin",
        "--keep-running",
        url,
        f"--mpv-force-media-title=Playing {title}",
        f"--mpv-slang={slang_val}",
        f"--mpv-user-agent={user_agent}",
    ]
    if _looks_direct(url):
        args.append("--mpv-ytdl=no")
    args.extend(quality_args)
    if referer:
        args.append(f"--mpv-referrer={referer}")
    for s_url in sub_urls:
        args.append(f"--mpv-sub-files={s_url}")
    return args


def _vlc_command(
    url: str,
    title: str,
    referer: str | None,
    chosen_sub_url: str | None,
    user_agent: str,
) -> list[str]:
    args = [
        "vlc",
        url,
        f"--meta-title=Playing {title}",
        f"--http-user-agent={user_agent}",
    ]
    if referer:
        args.append(f":http-referrer={referer}")
    if chosen_sub_url:
        args.append(f"--sub-file={chosen_sub_url}")
    return args


def _run_player(args: list[str], blocking: bool, report: bool = True) -> bool:
    """Launch a player and report when it bails out instead of failing silently.

    Returns ``True`` when the player ended normally, ``False`` otherwise.
    """
    if blocking:
        return subprocess.run(args, check=False).returncode in (0, 4)

    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL)
    code = proc.wait()
    if code not in (0, 4):
        if report:
            print(
                f"[!] The player exited with an error (code {code}). The host may "
                "be down, geo-blocked, or IP-bound."
            )
        return False
    return True


def play_stream(
    stream: StreamInfo,
    custom_player: str | None = None,
    sub_lang: str | None = None,
    report_failure: bool = True,
) -> bool:
    """Launch player for the given stream on macOS, Linux, Windows, or Termux (Android)."""
    cfg = get_config()
    chosen_player = (custom_player or cfg.player or "mpv").lower().strip()
    preferred_lang = (sub_lang or cfg.sub_language or "eng").lower()
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
    # Android (Termux) Playback via Android Intent (mimicking ani-cli and flix-cli)
    # -----------------------------------------------------------------------
    if is_android():
        player_type = chosen_player
        if player_type not in ("mpv", "vlc") and "/" not in player_type and "." not in player_type:
            player_type = "mpv"

        if player_type == "vlc":
            primary_name = "VLC"
            primary_comp = "org.videolan.vlc/org.videolan.vlc.gui.video.VideoPlayerActivity"
            fallback_name = "MPV"
            fallback_comp = "is.xyz.mpv/.MPVActivity"
        elif player_type == "mpv":
            primary_name = "MPV"
            primary_comp = "is.xyz.mpv/.MPVActivity"
            fallback_name = "VLC"
            fallback_comp = "org.videolan.vlc/org.videolan.vlc.gui.video.VideoPlayerActivity"
        else:
            primary_name = player_type
            primary_comp = player_type
            fallback_name = "MPV"
            fallback_comp = "is.xyz.mpv/.MPVActivity"

        # Setup MPV config file for session if MPV is primary or fallback (mimicking ani-cli)
        if primary_name == "MPV" or fallback_name == "MPV":
            setup_mpv_android_conf(
                referer=referer,
                sub_urls=sub_urls,
                preferred_sub=chosen_sub_url,
            )

        def _build_intent_args(component: str, name: str) -> list[str]:
            cmd = [
                "am",
                "start",
                "--user",
                "0",
                "-a",
                "android.intent.action.VIEW",
                "-d",
                url,
                "-n",
                component,
                "-e",
                "title",
                f"Playing {title}",
            ]
            if name == "MPV":
                # mpv-android accepts subtitle URLs via intent extras
                if sub_urls:
                    for s_url in sub_urls:
                        if s_url:
                            cmd.extend(["--esa", "subs", s_url])
                            cmd.extend(["--esa", "subtitles", s_url])
                            cmd.extend(["--esa", "subtitle_files", s_url])
                if chosen_sub_url:
                    cmd.extend(["--es", "sub-file", chosen_sub_url])
                    cmd.extend(["--es", "subfile", chosen_sub_url])
                    cmd.extend(["--es", "subs", chosen_sub_url])
                    cmd.extend(["--es", "subtitle", chosen_sub_url])
                    cmd.extend(["--es", "subtitles", chosen_sub_url])
            elif name == "VLC" and chosen_sub_url:
                cmd.extend(["--es", "subtitles_location", chosen_sub_url])
            return cmd

        print(f"\n[~] Android Detected: Launching {primary_name} Intent for '{title}' ~")
        primary_args = _build_intent_args(primary_comp, primary_name)

        try:
            res = subprocess.run(primary_args, capture_output=True, text=True)
            if res.returncode == 0 and "Error:" not in (res.stderr or "") and "Error:" not in (res.stdout or ""):
                print(f"[+] Stream opened in {primary_name}.")
                return True
            else:
                err = (res.stderr or res.stdout or "").strip()
                print(f"[!] {primary_name} intent launch failed: {err}")
        except Exception as e:
            print(f"[!] Error launching {primary_name}: {e}")

        # Attempt fallback player
        if fallback_comp:
            print(f"[~] Attempting fallback to {fallback_name}...")
            fallback_args = _build_intent_args(fallback_comp, fallback_name)
            try:
                fb_res = subprocess.run(fallback_args, capture_output=True, text=True)
                if fb_res.returncode == 0 and "Error:" not in (fb_res.stderr or "") and "Error:" not in (fb_res.stdout or ""):
                    print(f"[+] Stream opened in {fallback_name}.")
                    return True
                else:
                    fb_err = (fb_res.stderr or fb_res.stdout or "").strip()
                    print(f"[!] {fallback_name} intent launch failed: {fb_err}")
            except Exception as e:
                print(f"[!] Error launching {fallback_name}: {e}")

        # Final fallback to termux-open-url or generic VIEW intent
        if shutil.which("termux-open-url"):
            subprocess.run(["termux-open-url", url], check=False)
            return True

        try:
            subprocess.run(
                ["am", "start", "--user", "0", "-a", "android.intent.action.VIEW", "-d", url],
                check=False,
            )
            return True
        except Exception:
            pass

        return False

    # -----------------------------------------------------------------------
    # macOS Playback
    # -----------------------------------------------------------------------
    if system == "Darwin":
        if chosen_player == "iina" and shutil.which("iina"):
            return _run_player(
                _iina_command(
                    url,
                    title,
                    slang_val,
                    iina_quality_args,
                    referer,
                    sub_urls,
                    USER_AGENT,
                ),
                blocking=False,
                report=report_failure,
            )
        elif chosen_player == "vlc" and shutil.which("vlc"):
            return _run_player(
                _vlc_command(url, title, referer, chosen_sub_url, USER_AGENT),
                blocking=True,
                report=report_failure,
            )
        elif chosen_player == "mpv" and shutil.which("mpv"):
            return _run_player(
                _mpv_command(
                    "mpv",
                    url,
                    title,
                    slang_val,
                    mpv_quality_args,
                    referer,
                    sub_urls,
                    USER_AGENT,
                ),
                blocking=False,
                report=report_failure,
            )

        # Fallbacks for macOS
        if shutil.which("mpv"):
            return _run_player(
                _mpv_command(
                    "mpv",
                    url,
                    title,
                    slang_val,
                    mpv_quality_args,
                    referer,
                    sub_urls,
                    USER_AGENT,
                ),
                blocking=False,
                report=report_failure,
            )

        if shutil.which("iina"):
            return _run_player(
                _iina_command(
                    url,
                    title,
                    slang_val,
                    iina_quality_args,
                    referer,
                    sub_urls,
                    USER_AGENT,
                ),
                blocking=False,
                report=report_failure,
            )

        if shutil.which("vlc"):
            return _run_player(
                _vlc_command(url, title, referer, chosen_sub_url, USER_AGENT),
                blocking=True,
                report=report_failure,
            )

    # -----------------------------------------------------------------------
    # Linux / Windows / BSD
    # -----------------------------------------------------------------------
    if chosen_player == "vlc" and shutil.which("vlc"):
        return _run_player(
            _vlc_command(url, title, referer, chosen_sub_url, USER_AGENT),
            blocking=True,
            report=report_failure,
        )
    elif (chosen_player == "mpv" or chosen_player not in ("vlc", "iina")) and shutil.which(chosen_player):
        return _run_player(
            _mpv_command(
                chosen_player,
                url,
                title,
                slang_val,
                mpv_quality_args,
                referer,
                sub_urls,
                USER_AGENT,
            ),
            blocking=False,
            report=report_failure,
        )

    # Fallback to mpv if available
    if shutil.which("mpv"):
        return _run_player(
            _mpv_command(
                "mpv",
                url,
                title,
                slang_val,
                mpv_quality_args,
                referer,
                sub_urls,
                USER_AGENT,
            ),
            blocking=False,
            report=report_failure,
        )

    # Fallback to vlc if available
    if shutil.which("vlc"):
        return _run_player(
            _vlc_command(url, title, referer, chosen_sub_url, USER_AGENT),
            blocking=True,
            report=report_failure,
        )

    print("\n[!] No supported video player found. Please install mpv, iina, or vlc.")
    print(f"[!] Direct Stream URL: {url}")
    if sub_urls:
        print("[!] Subtitles available:")
        for s in sub_urls:
            print(f"    - {s}")
    return False
