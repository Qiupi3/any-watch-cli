from __future__ import annotations

import re
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
import httpx

from any_watch_core.base import (
    BaseProvider,
    EpisodeItem,
    MediaItem,
    MediaType,
    StreamInfo,
    SubtitleTrack,
)
from any_watch_core.extract import (
    DEFAULT_HEADERS,
    fetch_first,
    find_media_urls,
    origin,
    parse_year,
    resolve_stream,
)


IDLIX_BASE_URLS = (
    "https://idlixmovie.com",
    "https://idlix.lat",
    "https://idlix.com",
    "https://idlix.link",
)

_LANG_CODES = {
    "indonesian": "ind",
    "indonesia": "ind",
    "english": "eng",
    "malay": "msa",
    "chinese": "chi",
    "korean": "kor",
    "japanese": "jpn",
    "thai": "tha",
}


def _clean_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"\s*\(\d{4}\)\s*$", "", text)
    return text.strip(" -–—|")


def _slug_from_url(url: str) -> str:
    path = urlparse(url).path.strip("/")
    return path.split("/")[-1] if path else ""


def _episode_path(url: str) -> tuple[str, int | None, int | None]:
    """Return (slug, season, episode) from a watch/detail URL."""
    parsed = urlparse(url)
    parts = [part for part in parsed.path.split("/") if part]
    slug = parts[-1] if parts else ""
    query = parse_qs(parsed.query)
    season = query.get("season", [None])[0]
    episode = query.get("episode", [None])[0]
    try:
        season_num = int(season) if season is not None else None
    except (TypeError, ValueError):
        season_num = None
    try:
        episode_num = int(episode) if episode is not None else None
    except (TypeError, ValueError):
        episode_num = None
    return slug, season_num, episode_num


class IDLIXProvider(BaseProvider):
    name = "IDLIX"
    category = "Flix"
    base_urls = IDLIX_BASE_URLS

    async def search(self, query: str) -> list[MediaItem]:
        results: list[MediaItem] = []
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=15, follow_redirects=True
        ) as client:
            response, base = await fetch_first(
                client, self.base_urls, "/search", params={"q": query}
            )
            if response is None:
                return results

            soup = BeautifulSoup(response.text, "html.parser")
            seen: set[str] = set()
            for card in soup.select(".content-card, .grid-card"):
                anchor = card.select_one("a[href]")
                if anchor is None:
                    continue
                href = urljoin(str(response.url), anchor["href"])
                path = urlparse(href).path.lower()
                if not any(
                    path.startswith(prefix)
                    for prefix in ("/series/", "/movie/")
                ):
                    continue
                if href in seen:
                    continue

                title_node = card.select_one(".card-title")
                image = card.select_one("img[alt]")
                raw_title = (
                    title_node.get_text(" ", strip=True) if title_node else ""
                ) or (image.get("alt") if image else "")
                title = _clean_title(raw_title)
                if len(title) < 2:
                    title = _clean_title(_slug_from_url(href).replace("-", " "))

                type_node = card.select_one(".card-type")
                type_text = (
                    type_node.get_text(" ", strip=True).lower()
                    if type_node
                    else ""
                )
                is_series = path.startswith("/series/") or type_text in (
                    "tv",
                    "series",
                )
                seen.add(href)
                results.append(
                    MediaItem(
                        id=href,
                        title=title,
                        provider=self.name,
                        media_type=(
                            MediaType.SERIES if is_series else MediaType.MOVIE
                        ),
                        year=parse_year(raw_title),
                        category=self.category,
                        extra={"slug": _slug_from_url(href)},
                    )
                )

        return results

    async def _season_episodes(
        self,
        client: httpx.AsyncClient,
        page_url: str,
        slug: str,
        season: int,
        media_title: str,
    ) -> list[EpisodeItem]:
        api_url = urljoin(
            origin(page_url) + "/", f"api/series/{slug}/season/{season}"
        )
        try:
            response = await client.get(
                api_url,
                headers={
                    "Referer": page_url,
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            payload = response.json()
        except Exception:
            return []

        container = payload.get("season") if isinstance(payload, dict) else None
        if not isinstance(container, dict):
            container = payload if isinstance(payload, dict) else {}
        entries = container.get("episodes")
        if not isinstance(entries, list):
            return []

        episodes: list[EpisodeItem] = []
        watch_origin = origin(page_url) or self.base_urls[0]
        for entry in entries:
            number = str(entry.get("episodeNumber") or len(episodes) + 1)
            name = (entry.get("name") or "").strip()
            watch_url = (
                f"{watch_origin}/watch/series/{slug}"
                f"?season={season}&episode={number}"
            )
            episodes.append(
                EpisodeItem(
                    id=watch_url,
                    number=number,
                    title=name or f"Episode {number}",
                    season=season,
                    media_title=media_title,
                    extra={
                        "slug": slug,
                        "season": season,
                        "episode": number,
                        "type": "series",
                        "page": page_url,
                    },
                )
            )
        return episodes

    async def get_episodes(
        self, item: MediaItem, season: int | None = None
    ) -> list[EpisodeItem]:
        slug = (item.extra or {}).get("slug") or _slug_from_url(item.id)
        if item.media_type == MediaType.MOVIE:
            return [
                EpisodeItem(
                    id=item.id,
                    number="1",
                    title=item.title,
                    season=1,
                    media_title=item.title,
                    extra={"slug": slug, "type": "movie", "page": item.id},
                )
            ]

        episodes: list[EpisodeItem] = []
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=25, follow_redirects=True
        ) as client:
            try:
                response = await client.get(item.id)
            except Exception:
                return episodes

            page_url = str(response.url)
            soup = BeautifulSoup(response.text, "html.parser")

            season_numbers: list[int] = []
            for option in soup.select("#seasonSelect option[value]"):
                try:
                    season_numbers.append(int(option["value"]))
                except (TypeError, ValueError):
                    continue
            if not season_numbers:
                grid = soup.select_one("#epGrid[data-season]")
                if grid is not None:
                    try:
                        season_numbers = [int(grid["data-season"])]
                    except (TypeError, ValueError, KeyError):
                        season_numbers = []

            if season is not None:
                season_numbers = [value for value in season_numbers if value == season]
            if not season_numbers:
                season_numbers = [season or 1]

            for season_num in sorted(set(season_numbers)):
                episodes.extend(
                    await self._season_episodes(
                        client, page_url, slug, season_num, item.title
                    )
                )

            # Fallback: read the rendered grid for the currently selected season.
            if not episodes:
                seen: set[str] = set()
                for anchor in soup.select("#epGrid a.epcard[href]"):
                    href = urljoin(page_url, anchor["href"])
                    _, season_num, episode_num = _episode_path(href)
                    if href in seen or episode_num is None:
                        continue
                    seen.add(href)
                    number = str(episode_num)
                    episodes.append(
                        EpisodeItem(
                            id=href,
                            number=number,
                            title=anchor.get_text(" ", strip=True)
                            or f"Episode {number}",
                            season=season_num or season or 1,
                            media_title=item.title,
                            extra={
                                "slug": slug,
                                "season": season_num or season or 1,
                                "episode": number,
                                "type": "series",
                                "page": page_url,
                            },
                        )
                    )

        episodes.sort(key=lambda ep: (ep.season, int(re.sub(r"\D", "", ep.number) or 0)))
        return episodes

    async def get_stream(
        self, episode: EpisodeItem, quality: str | None = None
    ) -> StreamInfo:
        extra = episode.extra or {}
        slug = extra.get("slug") or _slug_from_url(episode.id)
        media_type = extra.get("type") or (
            "movie"
            if "/watch/movie/" in episode.id or "/movie/" in episode.id
            else "series"
        )
        season = extra.get("season")
        number = extra.get("episode")

        if extra.get("page"):
            watch_url = episode.id if episode.id.startswith("http") else extra["page"]
        else:
            watch_url = episode.id
        if not watch_url.startswith("http"):
            watch_url = urljoin(self.base_urls[0] + "/", watch_url)

        page_origin = origin(watch_url) or self.base_urls[0]

        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=30, follow_redirects=True
        ) as client:
            # Load the watch page first; it also sets any cookies the proxy needs.
            try:
                watch_page = await client.get(watch_url)
                page_url = str(watch_page.url)
                page_origin = origin(page_url) or page_origin
            except Exception:
                watch_page = None
                page_url = watch_url

            if media_type == "series":
                if season is None or number is None:
                    _, season, number = _episode_path(episode.id)
                suffix = ""
                if season is not None:
                    suffix = f"?season={season}&episode={number or 1}"
                api_url = (
                    f"{page_origin}/api/stream/series/{slug}{suffix}"
                )
            else:
                api_url = f"{page_origin}/api/stream/movie/{slug}"

            try:
                response = await client.get(
                    api_url,
                    headers={
                        "Referer": page_url,
                        "X-Requested-With": "XMLHttpRequest",
                    },
                )
                payload = response.json()
            except Exception:
                payload = {}

            stream_url = None
            subtitles: list[SubtitleTrack] = []
            if isinstance(payload, dict):
                candidates = payload.get("m3u8s") or []
                if not isinstance(candidates, list):
                    candidates = []
                if payload.get("configUrl"):
                    candidates = [*candidates, payload["configUrl"]]
                for candidate in candidates:
                    if candidate:
                        stream_url = urljoin(page_origin + "/", candidate)
                        break

                for subtitle in payload.get("subtitles") or []:
                    if not isinstance(subtitle, dict):
                        continue
                    src = subtitle.get("src") or subtitle.get("url")
                    if not src:
                        continue
                    label = subtitle.get("label") or "Indonesian"
                    lang = subtitle.get("lang") or _LANG_CODES.get(
                        label.lower(), "ind"
                    )
                    subtitles.append(
                        SubtitleTrack(
                            url=urljoin(page_origin + "/", src),
                            label=label,
                            lang=lang,
                        )
                    )

            if stream_url:
                return StreamInfo(
                    url=stream_url,
                    title=f"{episode.media_title} - {episode.display_name}",
                    referer=page_url,
                    subtitles=subtitles,
                    quality=quality,
                )

            # Some mirrors still render a plain iframe player. Only trust
            # iframes from external player hosts: IDLIX puts an autoplay ad
            # <video> on every watch page, so generic media scraping would
            # happily return that ad clip instead of the movie.
            if watch_page is not None:
                page = watch_page.text
                page_host = (urlparse(page_url).netloc or "").lower()
                soup = BeautifulSoup(page, "html.parser")
                for iframe in soup.select("iframe[src]"):
                    candidate = urljoin(page_url, iframe["src"].strip())
                    if not candidate.startswith("http"):
                        continue
                    host = (urlparse(candidate).netloc or "").lower()
                    if host == page_host or any(
                        token in host
                        for token in ("googletag", "doubleclick", "adsystem")
                    ):
                        continue
                    resolved, referer, subs = await resolve_stream(
                        client, candidate, referer=page_url
                    )
                    if resolved:
                        return StreamInfo(
                            url=resolved,
                            title=f"{episode.media_title} - {episode.display_name}",
                            referer=referer or page_url,
                            subtitles=subs,
                            quality=quality,
                        )

                for direct in find_media_urls(page):
                    if ".m3u8" not in direct.lower():
                        continue
                    return StreamInfo(
                        url=direct,
                        title=f"{episode.media_title} - {episode.display_name}",
                        referer=page_url,
                        quality=quality,
                    )

            raise RuntimeError(
                "IDLIX returned no video source for this title. The upstream "
                "provider has no stream for this movie/episode right now; try "
                "LK21 or FlixHQ for the same title."
            )
