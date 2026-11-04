from __future__ import annotations

"""HTML/JS stream extraction helpers shared by every scrape-based provider."""

import asyncio
import html as html_lib
import re
from typing import Iterable, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import httpx

from .base import SubtitleTrack

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
}

_M3U8_RE = re.compile(
    r"""https?://[^\s"'<>\\]+?/[^\s"'<>\\]*?\.m3u8(?:\?[^\s"'<>\\]*)?""",
    re.IGNORECASE,
)
_MP4_RE = re.compile(
    r"""https?://[^\s"'<>\\]+?/[^\s"'<>\\]*?\.mp4(?:\?[^\s"'<>\\]*)?(?=[\s"'<>\\,;]|$)""",
    re.IGNORECASE,
)

# File-hosting/landing pages that happen to contain ".mp4" in their path but
# never serve the media file itself. Resolving them requires a dedicated
# resolver (mp4upload) or is simply impossible because the host is defunct.
_NON_PLAYABLE_DOMAINS = (
    "mirrored.to",
    "mirrorace.com",
    "mirrorace.org",
    "oload.stream",
    "oload.tv",
    "openload.co",
    "uptobox.com",
    "solidfiles.com",
    "zippyshare.com",
    "userscloud.com",
    "uppit.com",
    "upfile.mobi",
    "mediafire.com",
    "mega.nz",
    "drive.google.com",
    "docs.google.com",
)


def _is_non_playable(url: str) -> bool:
    host = (urlparse(url).netloc or "").lower().split(":")[0]
    return any(
        host == domain or host.endswith(f".{domain}")
        for domain in _NON_PLAYABLE_DOMAINS
    )
_GVIDEO_RE = re.compile(
    r"""https?://[^\s"'<>\\]+?googlevideo\.com/videoplayback[^\s"'<>\\]*""",
    re.IGNORECASE,
)
_SUB_RE = re.compile(
    r"""https?://[^\s"'<>\\]+?/[^\s"'<>\\]*?\.(?:vtt|srt)(?:\?[^\s"'<>\\]*)?""",
    re.IGNORECASE,
)

_PACKER_RE = re.compile(
    r"""eval\(\s*function\(\s*p\s*,\s*a\s*,\s*c\s*,\s*k\s*,\s*e\s*,\s*[dr]\s*\)"""
    r"""\s*\{.*?\}\s*\(\s*['"](.*?)['"]\s*,\s*(\d+)\s*,\s*(\d+)\s*,"""
    r"""\s*['"](.*?)['"]\s*\.split\(\s*['"]\|['"]\s*\)""",
    re.DOTALL,
)

_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def origin(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return ""


def js_unescape(text: str) -> str:
    """Decode the most common JS/JSON escapes found in player payloads."""
    text = text.replace("\\/", "/")
    text = text.replace("\\u002F", "/").replace("\\u002f", "/")
    text = text.replace("\\u0026", "&").replace("\\u003d", "=")
    text = re.sub(
        r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text
    )
    text = re.sub(
        r"\\x([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), text
    )
    return text.replace('\\"', '"').replace("\\'", "'")


def _unbase(number: int, base: int) -> str:
    if number == 0:
        return _ALPHABET[0]
    out = ""
    while number:
        out = _ALPHABET[number % base] + out
        number //= base
    return out


def unpack_js(text: str) -> str:
    """Unpack Dean Edwards' p.a.c.k.e.r payloads used by file hosts."""
    match = _PACKER_RE.search(text)
    if not match:
        return ""

    payload, base, count, words_raw = match.groups()
    try:
        base_i = int(base) or 62
        count_i = int(count)
    except ValueError:
        return ""

    words = words_raw.split("|")
    unpacked = payload
    for index in range(count_i - 1, -1, -1):
        if index >= len(words) or not words[index]:
            continue
        token = _unbase(index, base_i)
        unpacked = re.sub(
            rf"\b{re.escape(token)}\b", lambda _m, w=words[index]: w, unpacked
        )
    return js_unescape(html_lib.unescape(unpacked))


def _clean_url(value: str) -> Optional[str]:
    """Normalise a regex URL match, rejecting escaped/concatenated fragments."""
    url = (value or "").strip().rstrip("\\,;)]}\"'")
    if url.startswith("//"):
        url = "https:" + url
    if not url.lower().startswith(("http://", "https://")):
        return None
    # Escaped JSON/HTML leaking into the match means it swallowed neighbours.
    if any(token in url for token in ("&quot;", "&#", "\\", '"', "'", "<", ">")):
        return None
    if url.lower().count("http") > 1:
        return None
    return url


def find_media_urls(page: str) -> list[str]:
    """Find playable m3u8/mp4/Blogger URLs in a page or player payload."""
    variants = [page, html_lib.unescape(page), js_unescape(html_lib.unescape(page))]
    unpacked = unpack_js(page)
    if unpacked:
        variants.extend([unpacked, js_unescape(html_lib.unescape(unpacked))])

    found: list[str] = []
    for variant in variants:
        for regex in (_M3U8_RE, _GVIDEO_RE, _MP4_RE):
            for match in regex.findall(variant):
                url = _clean_url(match)
                if url and not _is_non_playable(url) and url not in found:
                    found.append(url)

    def score(url: str) -> int:
        low = url.lower()
        value = 0
        if ".m3u8" in low:
            value += 50
        elif "googlevideo.com" in low:
            value += 45
            # Blogger googlevideo links are progressive MP4s: prefer 720p/1080p.
            itag = re.search(r"[?&]itag=(\d+)", low)
            if itag:
                value += {"37": 20, "22": 15, "18": 5}.get(itag.group(1), 0)
        elif ".mp4" in low:
            value += 30
        if any(bad in low for bad in ("trailer", "sample", "preview", "thumb")):
            value -= 40
        if any(good in low for good in ("cdn", "stream", "video", "player")):
            value += 5
        return value

    return sorted(found, key=score, reverse=True)


def find_subtitle_urls(page: str) -> list[str]:
    found: list[str] = []
    for variant in (page, html_lib.unescape(page), js_unescape(page)):
        for match in _SUB_RE.findall(variant):
            url = _clean_url(match)
            if url and url not in found:
                found.append(url)
    return found


def guess_lang(value: str) -> tuple[str, str]:
    low = value.lower()
    if any(tag in low for tag in ("ind", "indo", "id.", "/id", "_id", "bahasa")):
        return "Indonesian", "ind"
    if any(tag in low for tag in ("eng", "english", "en.", "/en", "_en")):
        return "English", "eng"
    if "may" in low or "msa" in low:
        return "Malay", "may"
    return "Subtitle", "other"


def subtitle_tracks(urls: Iterable[str]) -> list[SubtitleTrack]:
    tracks: list[SubtitleTrack] = []
    seen: set[str] = set()
    for url in urls:
        if url in seen:
            continue
        seen.add(url)
        label, lang = guess_lang(url)
        tracks.append(SubtitleTrack(url=url, label=label, lang=lang))
    return tracks


def find_embeds(page: str, base_url: str = "") -> list[str]:
    """Return iframe/player candidate URLs from a page."""
    embeds: list[str] = []
    soup = BeautifulSoup(page, "html.parser")

    attributes = ("src", "data-src", "data-video", "data-player", "data-iframe")
    for tag in soup.find_all(["iframe", "embed", "video", "source"]):
        for attr in attributes:
            value = tag.get(attr)
            if not value:
                continue
            url = urljoin(base_url, value.strip())
            if url.startswith("//"):
                url = "https:" + url
            if url.startswith("http") and url not in embeds:
                embeds.append(url)

    for tag in soup.find_all(attrs={"data-src": True}):
        value = (tag.get("data-src") or "").strip()
        if value.startswith("http") or value.startswith("//"):
            url = urljoin(base_url, value)
            if url.startswith("//"):
                url = "https:" + url
            if url not in embeds:
                embeds.append(url)

    for match in re.findall(
        r"""<iframe[^>]+(?:src|data-src)\s*=\s*["']([^"']+)["']""", page, re.I
    ):
        url = urljoin(base_url, match.strip())
        if url.startswith("//"):
            url = "https:" + url
        if url.startswith("http") and url not in embeds:
            embeds.append(url)

    return embeds


async def _resolve_mp4upload(
    client: httpx.AsyncClient, url: str, referer: str
) -> Optional[str]:
    """Resolve an mp4upload landing/embed page to its signed MP4 URL."""
    match = re.search(r"mp4upload\.com/(?:embed-)?([A-Za-z0-9]+)", url)
    if not match:
        return None

    file_id = match.group(1)
    page_url = f"https://www.mp4upload.com/{file_id}"
    headers = {
        **DEFAULT_HEADERS,
        "Origin": "https://www.mp4upload.com",
        "Referer": referer or page_url,
    }

    try:
        landing = await client.get(page_url, headers=headers)
        soup = BeautifulSoup(landing.text, "html.parser")
        form = soup.find("form", attrs={"name": "F1"}) or soup.find(
            "form", attrs={"method": re.compile("post", re.I)}
        )
        if form is None:
            return None

        data = {
            field.get("name", ""): field.get("value", "")
            for field in form.find_all("input")
            if field.get("name")
        }
        data.setdefault("id", file_id)
        data.setdefault("referer", page_url)
        data["method_free"] = data.get("method_free") or "Free Download"

        if data.get("op") != "download2":
            data["op"] = "download1"
            step = await client.post(page_url, data=data, headers=headers)
            soup = BeautifulSoup(step.text, "html.parser")
            form = soup.find("form", attrs={"name": "F1"}) or soup.find(
                "form", attrs={"method": re.compile("post", re.I)}
            )
            if form is None:
                return None
            data = {
                field.get("name", ""): field.get("value", "")
                for field in form.find_all("input")
                if field.get("name")
            }
            data.setdefault("id", file_id)
            data.setdefault("referer", page_url)
            data["method_free"] = data.get("method_free") or "Free Download"
            data["op"] = "download2"

        final = await client.post(
            page_url, data=data, headers=headers, follow_redirects=False
        )
        location = final.headers.get("location")
        if location:
            return urljoin(page_url, location)
    except Exception:
        return None
    return None


async def resolve_stream(
    client: httpx.AsyncClient,
    embed_url: str,
    referer: str = "",
    depth: int = 2,
    _seen: Optional[set[str]] = None,
) -> tuple[Optional[str], str, list[SubtitleTrack]]:
    """
    Follow an embed/iframe chain and return (playable_url, final_referer, subs).

    Handles direct files, HTML players, JS-packed payloads, Blogger video
    tokens, and nested iframes up to ``depth`` levels.
    """
    seen = _seen if _seen is not None else set()
    url = (embed_url or "").strip()
    if not url:
        return None, referer, []

    if url.startswith("//"):
        url = "https:" + url
    if url in seen:
        return None, referer, []
    seen.add(url)

    low = url.lower().split("?")[0]
    if _is_non_playable(url):
        return None, referer, []
    if low.endswith((".m3u8", ".mp4", ".webm")):
        return url, referer or origin(url), []

    if "mp4upload.com" in (urlparse(url).netloc or "").lower():
        resolved = await _resolve_mp4upload(client, url, referer)
        if resolved:
            return resolved, "https://www.mp4upload.com/", []
        return None, referer, []

    headers = dict(DEFAULT_HEADERS)
    if referer:
        headers["Referer"] = referer

    try:
        response = await client.get(url, headers=headers, timeout=15, follow_redirects=True)
    except Exception:
        return None, referer, []

    page = response.text or ""
    page_url = str(response.url)

    media = find_media_urls(page)
    if media:
        subs = subtitle_tracks(find_subtitle_urls(page))
        return media[0], page_url, subs

    if depth > 0:
        for child in find_embeds(page, page_url):
            if child in seen:
                continue
            media, final_referer, subs = await resolve_stream(
                client, child, referer=page_url, depth=depth - 1, _seen=seen
            )
            if media:
                return media, final_referer, subs

    return None, page_url, []


_SINGLE_USE_REDIRECT_RE = re.compile(
    r"^https?://[^/]*googlevideo\.com/videoplayback\?",
    re.IGNORECASE,
)


def is_single_use_url(url: str) -> bool:
    """True when the host answers with a one-shot redirect per URL.

    Google Video signs ``videoplayback`` links for the requesting IP and hands
    out a single ``302`` (``ipbypass``) to a matching edge. Consuming that
    redirect during validation leaves nothing for the player, so such URLs are
    returned untouched and resolved by the player itself.
    """
    return bool(url) and bool(_SINGLE_USE_REDIRECT_RE.match(url))


async def resolve_playable_url(
    client: httpx.AsyncClient,
    url: str,
    referer: str = "",
) -> Optional[str]:
    """Return the final playable URL, following CDN redirects.

    Single-use redirect URLs (googlevideo) are passed through untouched, since
    fetching them here would spend the only redirect the player needs.
    """
    if not url:
        return None

    if is_single_use_url(url):
        return url

    headers = {"Referer": referer} if referer else {}
    headers["Range"] = "bytes=0-4095"
    try:
        response = await client.get(
            url, headers=headers, timeout=20, follow_redirects=True
        )
    except Exception:
        return None

    if response.status_code not in (200, 206):
        return None

    # Playlists are often served from extension-less endpoints (``/api/hls?t=``)
    # or with a BOM, so inspect the body and content type instead of the URL.
    body = response.content.lstrip(b"\xef\xbb\xbf \t\r\n")
    if body.startswith(b"#EXTM3U"):
        return str(response.url)

    content_type = (response.headers.get("content-type") or "").lower()
    if "mpegurl" in content_type:
        return str(response.url)
    if content_type.startswith("video/"):
        return str(response.url)
    if response.content[4:8] == b"ftyp":
        return str(response.url)
    return None


async def is_stream_playable(
    client: httpx.AsyncClient,
    url: str,
    referer: str = "",
) -> bool:
    """Check that ``url`` really serves an HLS playlist or video bytes."""
    return await resolve_playable_url(client, url, referer) is not None


async def get_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    attempts: int = 3,
    backoff: float = 0.6,
    **kwargs,
) -> httpx.Response:
    """GET with a few retries for transient network failures.

    Several mirrors throttle bursts and drop the first connection; a short
    retry turns those flakes into successful reads without hiding real errors.
    """
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return await client.get(url, **kwargs)
        except httpx.TransportError as exc:
            last_error = exc
            if attempt + 1 < attempts:
                await asyncio.sleep(backoff * (attempt + 1))
    assert last_error is not None
    raise last_error


async def fetch_first(
    client: httpx.AsyncClient,
    bases: Iterable[str],
    path: str,
    params: Optional[dict] = None,
    headers: Optional[dict] = None,
) -> tuple[Optional[httpx.Response], str]:
    """Try mirrors in order and return the first useful response."""
    merged = dict(DEFAULT_HEADERS)
    if headers:
        merged.update(headers)
    for base in bases:
        base = base.rstrip("/")
        try:
            response = await get_with_retry(
                client,
                f"{base}{path}",
                params=params,
                headers=merged,
                timeout=12,
                follow_redirects=True,
            )
            if response.status_code < 400 and response.text.strip():
                return response, origin(str(response.url)) or base
        except Exception:
            continue
    return None, ""


def clean_title(title: str) -> str:
    title = re.sub(r"\s+", " ", html_lib.unescape(title or "")).strip()
    title = re.sub(r"\s*[\[(](?:download|batch|subtitle indonesia|sub indo)[\])]\s*", " ", title, flags=re.I)
    title = re.sub(r"\s+sub(?:title)?\s*indo(?:nesia)?\s*$", "", title, flags=re.I)
    return title.strip(" -–—|")


def parse_year(text: str) -> str:
    match = re.search(r"(?:19|20)\d{2}", text or "")
    return match.group(0) if match else ""


def episode_number(text: str) -> Optional[str]:
    patterns = (
        r"episode[\s_-]*(\d+(?:[.,]\d+)?)",
        r"\beps?[\s_.-]*(\d+(?:[.,]\d+)?)",
        r"\be(\d{1,4})\b",
        r"s\d+[\s_-]*e(\d+)",
    )
    for pattern in patterns:
        match = re.search(pattern, text or "", re.IGNORECASE)
        if match:
            return match.group(1).replace(",", ".")
    return None


def sort_key(number: str) -> float:
    try:
        return float(str(number).replace(",", "."))
    except (TypeError, ValueError):
        return 9999.0
