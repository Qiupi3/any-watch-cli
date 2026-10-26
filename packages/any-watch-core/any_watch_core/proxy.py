from __future__ import annotations

import re
import threading
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from any_watch_core.base import StreamInfo

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def srt_to_vtt(srt_text: str) -> str:
    """Convert SRT subtitle text to WebVTT format."""
    text = srt_text.strip()
    if text.startswith("WEBVTT"):
        return text
    # Convert comma decimal separators to dots: 00:01:23,456 -> 00:01:23.456
    vtt = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", text)
    return f"WEBVTT\n\n{vtt}"


class StreamProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        # Suppress noisy HTTP request logging in terminal
        pass

    @property
    def proxy(self) -> StreamProxy:
        return self.server.proxy  # type: ignore

    def do_HEAD(self) -> None:
        self._handle_request(head_only=True)

    def do_GET(self) -> None:
        self._handle_request(head_only=False)

    def _handle_request(self, head_only: bool = False) -> None:
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        try:
            if path in ("/master.m3u8", "/stream.m3u8"):
                self._handle_master_m3u8(head_only=head_only)
            elif path == "/proxy_variant":
                url = query.get("url", [""])[0]
                self._handle_proxy_variant(url, head_only=head_only)
            elif path in ("/proxy_segment", "/video"):
                url = query.get("url", [""])[0] or self.proxy.stream.url
                self._handle_proxy_stream(url, head_only=head_only)
            elif path.startswith("/sub_playlist/"):
                m = re.search(r"/sub_playlist/(\d+)\.m3u8", path)
                idx = int(m.group(1)) if m else 0
                self._handle_sub_playlist(idx, head_only=head_only)
            elif path.startswith("/sub/"):
                m = re.search(r"/sub/(\d+)", path)
                idx = int(m.group(1)) if m else 0
                as_vtt = path.endswith(".vtt") or not path.endswith(".srt")
                self._handle_sub_content(idx, as_vtt=as_vtt, head_only=head_only)
            else:
                self.send_error(404, "Not Found")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            try:
                self.send_error(500, f"Proxy Error: {e}")
            except Exception:
                pass

    def _make_upstream_request(self, url: str, headers: Optional[dict[str, str]] = None) -> urllib.request.Request:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", USER_AGENT)
        if self.proxy.stream.referer:
            req.add_header("Referer", self.proxy.stream.referer)
        if headers:
            for k, v in headers.items():
                req.add_header(k, v)
        return req

    def _handle_master_m3u8(self, head_only: bool) -> None:
        req = self._make_upstream_request(self.proxy.stream.url)
        with urllib.request.urlopen(req, timeout=12) as resp:
            content = resp.read().decode("utf-8", errors="replace")

        local_base = f"http://127.0.0.1:{self.proxy.port}"
        stream = self.proxy.stream
        lines = content.splitlines()

        # Build subtitle HLS lines if subtitles are available and not already in master
        has_embedded_subs = any("#EXT-X-MEDIA:TYPE=SUBTITLES" in l for l in lines)
        sub_lines = []
        if stream.subtitles and not has_embedded_subs:
            default_idx = self.proxy.default_sub_idx
            for i, sub in enumerate(stream.subtitles):
                is_def = "YES" if i == default_idx else "NO"
                label = getattr(sub, "label", f"Subtitle {i+1}")
                lang = getattr(sub, "lang", "und")
                sub_uri = f"{local_base}/sub_playlist/{i}.m3u8"
                sub_lines.append(
                    f'#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="subs",NAME="{label}",'
                    f'DEFAULT={is_def},AUTOSELECT=YES,FORCED=NO,LANGUAGE="{lang}",URI="{sub_uri}"'
                )

        new_lines = []
        inserted_subs = False
        expecting_variant_uri = False

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            if stripped.startswith("#EXT-X-STREAM-INF:") and sub_lines:
                if 'SUBTITLES=' not in stripped:
                    stripped = stripped + ',SUBTITLES="subs"'
                new_lines.append(stripped)
                expecting_variant_uri = True
                continue

            if expecting_variant_uri and not stripped.startswith("#"):
                expecting_variant_uri = False
                abs_variant_url = urllib.parse.urljoin(stream.url, stripped)
                proxied_url = f"{local_base}/proxy_variant?url={urllib.parse.quote(abs_variant_url)}"
                new_lines.append(proxied_url)
                continue

            new_lines.append(stripped)
            if not inserted_subs and (stripped.startswith("#EXTM3U") or stripped.startswith("#EXT-X-VERSION")):
                new_lines.extend(sub_lines)
                inserted_subs = True

        out_body = "\n".join(new_lines).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl")
        self.send_header("Content-Length", str(len(out_body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if not head_only:
            self.wfile.write(out_body)

    def _handle_proxy_variant(self, url: str, head_only: bool) -> None:
        if not url:
            self.send_error(400, "Missing url parameter")
            return

        req = self._make_upstream_request(url)
        with urllib.request.urlopen(req, timeout=12) as resp:
            content = resp.read().decode("utf-8", errors="replace")

        local_base = f"http://127.0.0.1:{self.proxy.port}"
        lines = content.splitlines()
        new_lines = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                if stripped.startswith("#EXT-X-MAP:URI="):
                    m = re.search(r'#EXT-X-MAP:URI="([^"]+)"', stripped)
                    if m:
                        map_url = urllib.parse.urljoin(url, m.group(1))
                        proxied = f"{local_base}/proxy_segment?url={urllib.parse.quote(map_url)}"
                        stripped = f'#EXT-X-MAP:URI="{proxied}"'
                new_lines.append(stripped)
            else:
                abs_seg = urllib.parse.urljoin(url, stripped)
                # Proxy segments through local proxy if upstream requires Referer
                if self.proxy.stream.referer:
                    new_lines.append(f"{local_base}/proxy_segment?url={urllib.parse.quote(abs_seg)}")
                else:
                    new_lines.append(abs_seg)

        out_body = "\n".join(new_lines).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl")
        self.send_header("Content-Length", str(len(out_body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if not head_only:
            self.wfile.write(out_body)

    def _handle_proxy_stream(self, url: str, head_only: bool) -> None:
        headers = {}
        if "Range" in self.headers:
            headers["Range"] = self.headers["Range"]

        req = self._make_upstream_request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=15) as resp:
            code = resp.status
            self.send_response(code)
            for header_name in ("Content-Type", "Content-Length", "Content-Range", "Accept-Ranges"):
                val = resp.headers.get(header_name)
                if val:
                    self.send_header(header_name, val)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            if not head_only:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

    def _handle_sub_playlist(self, idx: int, head_only: bool) -> None:
        local_base = f"http://127.0.0.1:{self.proxy.port}"
        sub_uri = f"{local_base}/sub/{idx}.vtt"
        m3u8 = (
            "#EXTM3U\n"
            "#EXT-X-TARGETDURATION:7200\n"
            "#EXT-X-VERSION:3\n"
            "#EXT-X-MEDIA-SEQUENCE:0\n"
            "#EXTINF:7200.0,\n"
            f"{sub_uri}\n"
            "#EXT-X-ENDLIST\n"
        ).encode("utf-8")

        self.send_response(200)
        self.send_header("Content-Type", "application/vnd.apple.mpegurl")
        self.send_header("Content-Length", str(len(m3u8)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if not head_only:
            self.wfile.write(m3u8)

    def _handle_sub_content(self, idx: int, as_vtt: bool, head_only: bool) -> None:
        if not self.proxy.stream.subtitles or idx >= len(self.proxy.stream.subtitles):
            self.send_error(404, "Subtitle Not Found")
            return

        sub_track = self.proxy.stream.subtitles[idx]
        sub_url = getattr(sub_track, "url", str(sub_track))
        req = self._make_upstream_request(sub_url)

        with urllib.request.urlopen(req, timeout=10) as resp:
            raw_text = resp.read().decode("utf-8", errors="replace")

        if as_vtt:
            out_text = srt_to_vtt(raw_text)
            content_type = "text/vtt; charset=utf-8"
        else:
            out_text = raw_text
            content_type = "text/plain; charset=utf-8"

        out_bytes = out_text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(out_bytes)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if not head_only:
            self.wfile.write(out_bytes)


class StreamProxy:
    def __init__(self, stream: StreamInfo, preferred_lang: str = "ind") -> None:
        self.stream = stream
        self.preferred_lang = preferred_lang.lower()
        self.server = HTTPServer(("127.0.0.1", 0), StreamProxyHandler)
        self.server.proxy = self  # type: ignore
        self.port = self.server.server_port
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()

    @property
    def default_sub_idx(self) -> int:
        if not self.stream.subtitles:
            return -1

        pref = self.preferred_lang
        # 1. Match preferred language
        for i, s in enumerate(self.stream.subtitles):
            s_lang = getattr(s, "lang", "").lower()
            s_label = getattr(s, "label", "").lower()
            if pref in s_lang or pref in s_label or ("ind" in pref and ("id" in s_lang or "indo" in s_label)):
                return i

        # 2. Fallback to English
        for i, s in enumerate(self.stream.subtitles):
            s_lang = getattr(s, "lang", "").lower()
            s_label = getattr(s, "label", "").lower()
            if "eng" in s_lang or "en" in s_lang or "english" in s_label:
                return i

        # 3. Fallback to first available
        return 0

    def get_play_url(self) -> str:
        """Returns the local proxy URL to feed to MPV/VLC."""
        url_lower = self.stream.url.lower().split("?")[0]
        if ".m3u8" in url_lower:
            return f"http://127.0.0.1:{self.port}/master.m3u8"
        else:
            return f"http://127.0.0.1:{self.port}/video"

    def get_chosen_sub_url(self) -> str | None:
        """Returns the local subtitle URL for external players like VLC Android."""
        idx = self.default_sub_idx
        if idx >= 0:
            return f"http://127.0.0.1:{self.port}/sub/{idx}.vtt"
        return None

    def stop(self) -> None:
        try:
            self.server.shutdown()
            self.server.server_close()
        except Exception:
            pass
