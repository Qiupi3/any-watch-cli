from __future__ import annotations

import base64
import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import httpx

from any_watch_core.base import (
    MAX_ALTERNATES,
    BaseProvider,
    EpisodeItem,
    MediaItem,
    MediaType,
    StreamInfo,
    with_alternates,
)
from any_watch_core.extract import (
    DEFAULT_HEADERS,
    episode_number,
    fetch_first,
    find_embeds,
    find_media_urls,
    find_subtitle_urls,
    origin,
    parse_year,
    resolve_playable_url,
    resolve_stream,
    sort_key,
    subtitle_tracks,
)


OTAKUDESU_BASE_URLS = (
    "https://otakudesu.blog",
    "https://otakudesu.cloud",
    "https://otakudesu.camera",
    "https://otakudesu.best",
)

# OtakuDesu's player is served by two rotating AJAX actions: the first returns
# a nonce, the second returns base64-encoded player HTML for a mirror entry.
_NONCE_ACTION = "aa1208d27f29ca340c92c66d1926f13f"
_PLAYER_ACTION = "2a3505c93b0035d3f455df82bf976b84"

# Hosts that are known to be permanently dead or that cannot be played without
# a browser (Mega) - skip them so we do not waste the user's time.
_SKIP_EMBED_HOSTS = (

    "mega.nz",
    "mega.co.nz",
    "desustream.com/maintenance",
)


def _decode_mirror(data_content: str) -> dict | None:
    try:
        raw = base64.b64decode(data_content + "===")
        payload = json.loads(raw.decode("utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _quality_rank(quality: str) -> int:
    match = re.search(r"(\d{3,4})", quality or "")
    return int(match.group(1)) if match else 0


class OtakuDesuProvider(BaseProvider):
    name = "OtakuDesu"
    category = "Anime"
    base_urls = OTAKUDESU_BASE_URLS

    async def search(self, query: str) -> list[MediaItem]:
        results: list[MediaItem] = []
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=15, follow_redirects=True
        ) as client:
            response, base = await fetch_first(
                client,
                self.base_urls,
                "/",
                params={"s": query, "post_type": "anime"},
            )
            if response is None:
                return results

            soup = BeautifulSoup(response.text, "html.parser")
            seen: set[str] = set()
            for item in soup.select(".chivsrc li, .chivsrc .chivsrc-item, article"):
                anchor = item.select_one("h2 a, h3 a, .title a, a[href*='/anime/']")
                if not anchor:
                    continue
                href = urljoin(base, anchor.get("href", ""))
                if "/anime/" not in href or href in seen:
                    continue
                title = anchor.get_text(" ", strip=True)
                if not title:
                    continue
                seen.add(href)
                results.append(
                    MediaItem(
                        id=href,
                        title=re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip(),
                        provider=self.name,
                        media_type=MediaType.ANIME,
                        year=parse_year(item.get_text(" ", strip=True)),
                        category=self.category,
                    )
                )

        return results

    async def get_episodes(
        self, item: MediaItem, season: int | None = None
    ) -> list[EpisodeItem]:
        episodes: list[EpisodeItem] = []
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=15, follow_redirects=True
        ) as client:
            response = await client.get(item.id)
            soup = BeautifulSoup(response.text, "html.parser")

            seen: set[str] = set()
            for anchor in soup.select(".episodelist ul li a, .episodelist a[href]"):
                href = urljoin(item.id, anchor.get("href", ""))
                text = anchor.get_text(" ", strip=True)
                # The list also contains a "Batch" entry that links to the
                # /lengkap/ page for the whole series; it is not an episode.
                if "/lengkap/" in href or "/batch/" in href:
                    continue
                if "batch" in text.lower() or "download" in text.lower():
                    continue
                if href in seen:
                    continue
                number = episode_number(f"{href} {text}")
                if not number:
                    match = re.search(r"episode[- ]?(\d+(?:\.\d+)?)", href, re.I)
                    number = match.group(1) if match else str(len(episodes) + 1)
                seen.add(href)
                episodes.append(
                    EpisodeItem(
                        id=href,
                        number=number,
                        title=text or f"Episode {number}",
                        season=season or 1,
                        media_title=item.title,
                    )
                )

            episodes.sort(key=lambda ep: sort_key(ep.number))
        return episodes

    async def _fetch_nonce(
        self, client: httpx.AsyncClient, page_url: str
    ) -> str | None:
        try:
            response = await client.post(
                urljoin(origin(page_url) + "/", "wp-admin/admin-ajax.php"),
                data={"action": _NONCE_ACTION},
                headers={
                    "Referer": page_url,
                    "Origin": origin(page_url),
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            payload = response.json()
        except Exception:
            return None
        nonce = payload.get("data") if isinstance(payload, dict) else None
        return nonce if isinstance(nonce, str) and nonce else None

    async def _player_html(
        self,
        client: httpx.AsyncClient,
        page_url: str,
        nonce: str,
        mirror: dict,
    ) -> str:
        data = {
            "id": mirror.get("id", ""),
            "i": mirror.get("i", 0),
            "q": mirror.get("q", ""),
            "nonce": nonce,
            "action": _PLAYER_ACTION,
        }
        try:
            response = await client.post(
                urljoin(origin(page_url) + "/", "wp-admin/admin-ajax.php"),
                data=data,
                headers={
                    "Referer": page_url,
                    "Origin": origin(page_url),
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            payload = response.json()
        except Exception:
            return ""
        encoded = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(encoded, str) or not encoded:
            return ""
        try:
            return base64.b64decode(encoded).decode("utf-8", "replace")
        except Exception:
            return ""

    async def get_stream(
        self, episode: EpisodeItem, quality: str | None = None
    ) -> StreamInfo:
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=25, follow_redirects=True
        ) as client:
            response = await client.get(episode.id)
            page = response.text
            page_url = str(response.url)
            soup = BeautifulSoup(page, "html.parser")

            mirrors: list[dict] = []
            for anchor in soup.select(".mirrorstream a[data-content], a[data-content]"):
                decoded = _decode_mirror(anchor.get("data-content", ""))
                if decoded and decoded.get("id"):
                    mirrors.append(decoded)
            mirrors.sort(
                key=lambda mirror: -_quality_rank(str(mirror.get("q") or ""))
            )

            embed_candidates: list[str] = []
            if mirrors:
                nonce = await self._fetch_nonce(client, page_url)
                for mirror in mirrors:
                    if not nonce:
                        break
                    player_html = await self._player_html(
                        client, page_url, nonce, mirror
                    )
                    if not player_html:
                        continue
                    player_soup = BeautifulSoup(player_html, "html.parser")
                    for tag in player_soup.find_all("iframe"):
                        src = (tag.get("src") or "").strip()
                        if not src:
                            continue
                        embed = urljoin(page_url, src)
                        if embed not in embed_candidates:
                            embed_candidates.append(embed)
                    for embed in find_embeds(player_html, page_url):
                        if embed not in embed_candidates:
                            embed_candidates.append(embed)
                    for direct in find_media_urls(player_html):
                        if direct not in embed_candidates:
                            embed_candidates.append(direct)

            embed_candidates.extend(
                embed
                for embed in find_embeds(page, page_url)
                if embed not in embed_candidates
            )

            title = f"{episode.media_title} - {episode.display_name}"
            found: list[StreamInfo] = []

            def _keep(stream: StreamInfo) -> bool:
                if all(stream.url != kept.url for kept in found):
                    found.append(stream)
                return len(found) >= MAX_ALTERNATES

            for candidate in embed_candidates:
                low = candidate.lower()
                if any(host in low for host in _SKIP_EMBED_HOSTS):
                    continue
                stream_url, referer, subs = await resolve_stream(
                    client, candidate, referer=page_url
                )
                if not stream_url:
                    continue
                # Mirror hosts hand out IP-bound or expired googlevideo links;
                # only return sources that actually serve media bytes, and keep
                # the post-redirect URL the player can fetch directly.
                final_url = await resolve_playable_url(
                    client, stream_url, referer=referer or page_url
                )
                if not final_url:
                    continue
                if _keep(
                    StreamInfo(
                        url=final_url,
                        title=title,
                        referer=referer or page_url,
                        subtitles=subs,
                        quality=quality,
                    )
                ):
                    break

            if not found:
                for media_url in find_media_urls(page):
                    final_url = await resolve_playable_url(
                        client, media_url, referer=page_url
                    )
                    if not final_url:
                        continue
                    if _keep(
                        StreamInfo(
                            url=final_url,
                            title=title,
                            referer=page_url,
                            subtitles=subtitle_tracks(find_subtitle_urls(page)),
                            quality=quality,
                        )
                    ):
                        break

            if found:
                return with_alternates(found)

            raise RuntimeError(
                "OtakuDesu returned no playable mirror for this episode. Its "
                "hosts (desustream/mp4upload/mega) rotate often; try another "
                "episode, or use Samehadaku/AnoBoy."
            )
