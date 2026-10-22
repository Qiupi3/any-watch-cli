import subprocess
from urllib.parse import parse_qs, urlparse

import httpx
import regex

headers = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def decrypt_stream_url(
    embed_link: str, quality: str | None = None, subs_language: str = "english"
) -> tuple[str | None, list[str] | None]:
    video_link = None
    subs_links: list[str] = []

    with httpx.Client(headers=headers, follow_redirects=True, timeout=10) as client:
        # 1. Extract subtitles from query parameters if present (e.g. ?subget=... or ?sub.info=...)
        try:
            parsed = urlparse(embed_link)
            qs = parse_qs(parsed.query)
            sub_urls = qs.get("subget", []) + qs.get("sub.info", [])
            for sub_url in sub_urls:
                try:
                    sub_resp = client.get(sub_url, timeout=5)
                    if sub_resp.status_code == 200:
                        tracks = sub_resp.json()
                        if isinstance(tracks, list):
                            for track in tracks:
                                if isinstance(track, dict) and "file" in track:
                                    label = track.get("label", "")
                                    if regex.search(rf"{subs_language}", label, regex.IGNORECASE):
                                        subs_links.append(track["file"])
                            if not subs_links and tracks and isinstance(tracks[0], dict) and "file" in tracks[0]:
                                subs_links.append(tracks[0]["file"])
                except Exception:
                    pass
        except Exception:
            pass

        # 2. Check if embed_link is already a direct video stream
        clean_url = embed_link.split("?")[0]
        if clean_url.endswith(".m3u8") or clean_url.endswith(".mp4"):
            video_link = clean_url

        # 3. Direct scraping from embed page (e.g. Vidmoly / kaembed.net)
        if not video_link:
            for target_url in [embed_link, clean_url]:
                try:
                    resp = client.get(target_url, timeout=6)
                    if resp.status_code == 200:
                        m3u8_match = regex.search(r'https?://[^\s\"\'\<\>]*\.m3u8[^\s\"\'\<\>]*', resp.text)
                        if m3u8_match:
                            video_link = m3u8_match.group(0)

                        if not subs_links:
                            track_matches = regex.findall(r'https?://[^\s"\'<>]+\.vtt', resp.text)
                            for tr in track_matches:
                                if tr not in subs_links:
                                    subs_links.append(tr)

                        if video_link:
                            break
                except Exception:
                    continue

        # 4. Fallback to yt-dlp to extract stream if not yet found
        if not video_link:
            try:
                cmd = ["yt-dlp", "-g", "--no-warnings", "--referer", "https://flixhqz.net/", embed_link]
                ytdl_res = subprocess.check_output(cmd, stderr=subprocess.DEVNULL, timeout=12)
                ytdl_url = ytdl_res.decode("utf-8").strip().splitlines()
                if ytdl_url:
                    video_link = ytdl_url[0]
            except Exception:
                pass

    if video_link and quality:
        video_link = regex.sub(r"/playlist\.m3u8", f"/{quality}/index.m3u8", video_link)

    return video_link, subs_links
