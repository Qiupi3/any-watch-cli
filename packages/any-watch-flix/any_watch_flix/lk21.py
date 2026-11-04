from __future__ import annotations

import json
import re
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
import httpx

from any_watch_core.base import (
    BaseProvider,
    EpisodeItem,
    MediaItem,
    MediaType,
    StreamInfo,
)
from any_watch_core.extract import (
    DEFAULT_HEADERS,
    fetch_first,
    find_embeds,
    find_media_urls,
    find_subtitle_urls,
    origin,
    resolve_stream,
    subtitle_tracks,
)


LK21_BASE_URLS = (
    "https://tv12.lk21official.cc",
    "https://lk21.de",
)

# The site exposes its search backend through ``data-search_url`` on <body>.
# Only used when that attribute cannot be read from a live mirror.
_SEARCH_FALLBACK = "https://gudangvape.com/"

_SEARCH_URL_RE = re.compile(
    r"""data-search_url\s*=\s*["']([^"']+)["']""", re.IGNORECASE
)
_WATCH_MARKERS = ('id="main-player"', "season-data", 'id="videoAd"')
_INTERSTITIAL_MARKERS = ("nontondrama", "dramamu.lk21")


def _clean_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"^(?:nonton|download|watch)\s+", "", text, flags=re.I)
    text = re.sub(r"\s*[-–—]\s*series\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+(?:sub\s*indo|subtitle indonesia)\s*$", "", text, flags=re.I)
    text = re.sub(r"\s*\(\d{4}\)\s*$", "", text)
    return text.strip(" -–—|")


def _is_watch_page(page: str) -> bool:
    return any(marker in page for marker in _WATCH_MARKERS)


class LK21Provider(BaseProvider):
    name = "LK21"
    category = "Flix"
    base_urls = LK21_BASE_URLS

    async def search(self, query: str) -> list[MediaItem]:
        results: list[MediaItem] = []
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=15, follow_redirects=True
        ) as client:
            home, base = await fetch_first(client, self.base_urls, "/")
            if home is None:
                return results

            search_root = _SEARCH_FALLBACK
            match = _SEARCH_URL_RE.search(home.text)
            if match:
                search_root = urljoin(str(home.url), match.group(1))

            try:
                response = await client.get(
                    urljoin(search_root, "search.php"),
                    params={"s": query, "page": 1},
                    headers={
                        "Referer": str(home.url),
                        "X-Requested-With": "XMLHttpRequest",
                    },
                )
                payload = response.json()
            except Exception:
                return results

            entries = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(entries, list):
                return results

            for entry in entries:
                slug = (entry.get("slug") or "").strip()
                if not slug:
                    continue
                href = urljoin(base, f"/{slug}")
                raw_type = (entry.get("type") or "").lower()
                is_series = raw_type == "series" or int(entry.get("episode") or 0) > 0
                results.append(
                    MediaItem(
                        id=href,
                        title=_clean_title(entry.get("title") or slug),
                        provider=self.name,
                        media_type=(
                            MediaType.SERIES if is_series else MediaType.MOVIE
                        ),
                        year=str(entry.get("year") or ""),
                        category=self.category,
                        extra={
                            "slug": slug,
                            "poster": entry.get("poster") or "",
                            "type": raw_type,
                        },
                    )
                )

        return results

    async def _resolve_watch_page(
        self, client: httpx.AsyncClient, url: str
    ) -> httpx.Response:
        """Follow LK21's redirect/interstitial chain to the actual watch page."""
        response = await client.get(url)
        if _is_watch_page(response.text):
            return response

        soup = BeautifulSoup(response.text, "html.parser")
        candidates: list[str] = []
        body = soup.find("body")
        page_slug = (body.get("data-page") or "").strip() if body else ""
        if page_slug:
            candidates.append(
                urljoin(str(response.url), f"https://dramamu.lk21.de/{page_slug}")
            )
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            if any(marker in href for marker in _INTERSTITIAL_MARKERS):
                candidates.append(urljoin(str(response.url), href))
            elif "nontondrama" in href and "page=" in href:
                candidates.append(urljoin(str(response.url), href))

        for candidate in candidates:
            try:
                follow = await client.get(candidate)
            except Exception:
                continue
            if _is_watch_page(follow.text):
                return follow

        return response

    async def get_episodes(
        self, item: MediaItem, season: int | None = None
    ) -> list[EpisodeItem]:
        if item.media_type == MediaType.MOVIE:
            return [
                EpisodeItem(
                    id=item.id,
                    number="1",
                    title=item.title,
                    season=1,
                    media_title=item.title,
                    extra={"page": item.id},
                )
            ]

        episodes: list[EpisodeItem] = []
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=20, follow_redirects=True
        ) as client:
            try:
                response = await self._resolve_watch_page(client, item.id)
            except Exception:
                return episodes

            page = response.text
            page_origin = origin(str(response.url)) or origin(item.id)

            match = re.search(
                r'<script id="season-data"[^>]*>(.*?)</script>', page, re.S
            )
            if match:
                try:
                    seasons = json.loads(match.group(1))
                except Exception:
                    seasons = {}
                if isinstance(seasons, dict):
                    for key, entries in seasons.items():
                        if not isinstance(entries, list):
                            continue
                        try:
                            season_num = int(key)
                        except (TypeError, ValueError):
                            season_num = 1
                        if season is not None and season_num != season:
                            continue
                        for entry in entries:
                            slug = (entry.get("slug") or "").strip()
                            if not slug:
                                continue
                            number = str(entry.get("episode_no") or len(episodes) + 1)
                            episodes.append(
                                EpisodeItem(
                                    id=urljoin(page_origin + "/", slug),
                                    number=number,
                                    title=entry.get("title")
                                    or f"Episode {number}",
                                    season=season_num,
                                    media_title=item.title,
                                    extra={"page": str(response.url)},
                                )
                            )

            if not episodes:
                soup = BeautifulSoup(page, "html.parser")
                seen: set[str] = set()
                for anchor in soup.find_all("a", href=True):
                    href = urljoin(str(response.url), anchor["href"])
                    haystack = f"{href} {anchor.get_text(' ', strip=True)}".lower()
                    if "episode" not in haystack and "-episode-" not in haystack:
                        continue
                    if href in seen or href == str(response.url):
                        continue
                    number_match = re.search(
                        r"episode[-_ ]?(\d+(?:[.,]\d+)?)", haystack
                    )
                    number = number_match.group(1) if number_match else str(
                        len(episodes) + 1
                    )
                    seen.add(href)
                    episodes.append(
                        EpisodeItem(
                            id=href,
                            number=number,
                            title=anchor.get_text(" ", strip=True)
                            or f"Episode {number}",
                            season=season or 1,
                            media_title=item.title,
                            extra={"page": str(response.url)},
                        )
                    )

        episodes.sort(
            key=lambda ep: (ep.season, int(re.sub(r"\D", "", ep.number) or 0))
        )
        if not episodes:
            episodes = [
                EpisodeItem(
                    id=item.id,
                    number="1",
                    title=item.title,
                    season=1,
                    media_title=item.title,
                    extra={"page": item.id},
                )
            ]
        return episodes

    async def _resolve_playcdn(
        self, client: httpx.AsyncClient, embed_url: str
    ) -> tuple[str | None, str]:
        """Resolve a playcdn.de embed page to its HLS playlist."""
        if not embed_url:
            return None, ""
        if embed_url.lower().split("?")[0].endswith(
            (".m3u8", ".mp4", ".webm")
        ):
            return embed_url, embed_url

        parsed = urlparse(embed_url)
        if "playcdn.de" not in (parsed.netloc or "").lower():
            return None, ""

        slug = parsed.path.strip("/").split("/")[0]
        if not slug:
            return None, ""

        verify_url = f"{origin(embed_url)}/verify/{slug}"
        try:
            response = await client.get(
                verify_url, headers={"Referer": embed_url}
            )
            data = response.json()
        except Exception:
            return None, ""

        file_url = data.get("fileUrl") if isinstance(data, dict) else None
        if not file_url:
            return None, ""
        return urljoin(embed_url, file_url), embed_url

    async def _resolve_videonode(
        self, client: httpx.AsyncClient, player_url: str
    ) -> tuple[str | None, str]:
        match = re.search(
            r"videonode\.de/iframe3/([^/?#]+)/([^/?#]+)", player_url
        )
        if not match:
            return None, ""
        host, video_id = match.group(1), match.group(2)
        if host != "p2p":
            return None, ""
        try:
            response = await client.post(
                "https://videonode.de/api.php",
                data={"host": host, "id": video_id},
                headers={
                    "Referer": player_url,
                    "Origin": "https://videonode.de",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            data = response.json()
        except Exception:
            return None, ""
        embed_url = data.get("embedUrl") if isinstance(data, dict) else None
        if not embed_url:
            return None, ""
        return await self._resolve_playcdn(
            client, urljoin(player_url, embed_url)
        )

    async def get_stream(
        self, episode: EpisodeItem, quality: str | None = None
    ) -> StreamInfo:
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=25, follow_redirects=True
        ) as client:
            try:
                response = await self._resolve_watch_page(client, episode.id)
            except Exception as exc:
                raise RuntimeError(
                    f"LK21 could not open the episode page: {episode.id}"
                ) from exc

            page = response.text
            page_url = str(response.url)
            soup = BeautifulSoup(page, "html.parser")

            player_urls: list[str] = []
            main_player = soup.select_one("#main-player")
            if main_player is not None and main_player.get("src"):
                player_urls.append(
                    urljoin(page_url, str(main_player["src"]))
                )
            for tag in soup.select("[data-url]"):
                value = (tag.get("data-url") or "").strip()
                if value:
                    url = urljoin(page_url, value)
                    if url not in player_urls:
                        player_urls.append(url)
            for embed in find_embeds(page, page_url):
                if embed not in player_urls:
                    player_urls.append(embed)

            # Prefer the p2p player: its token endpoint is stable and returns
            # a playcdn HLS URL directly.
            ordered = sorted(
                player_urls,
                key=lambda url: 0 if "/iframe3/p2p/" in url else 1,
            )

            for player_url in ordered:
                stream_url, referer = await self._resolve_videonode(
                    client, player_url
                )
                if stream_url:
                    return StreamInfo(
                        url=stream_url,
                        title=f"{episode.media_title} - {episode.display_name}",
                        referer=referer or player_url,
                        subtitles=subtitle_tracks(
                            find_subtitle_urls(page)
                        ),
                        quality=quality,
                    )

                stream_url, referer, subs = await resolve_stream(
                    client, player_url, referer=page_url
                )
                if stream_url:
                    return StreamInfo(
                        url=stream_url,
                        title=f"{episode.media_title} - {episode.display_name}",
                        referer=referer or page_url,
                        subtitles=subs,
                        quality=quality,
                    )

            direct = find_media_urls(page)
            if direct:
                return StreamInfo(
                    url=direct[0],
                    title=f"{episode.media_title} - {episode.display_name}",
                    referer=page_url,
                    subtitles=subtitle_tracks(find_subtitle_urls(page)),
                    quality=quality,
                )

            raise RuntimeError(
                "LK21 did not expose a playable player for this episode. "
                "The mirror may be serving an ad-only player; try another "
                "episode or mirror."
            )
