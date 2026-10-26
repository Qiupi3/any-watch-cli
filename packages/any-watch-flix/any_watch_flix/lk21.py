from __future__ import annotations

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
    episode_number,
    fetch_first,
    find_embeds,
    find_media_urls,
    find_subtitle_urls,
    origin,
    parse_year,
    resolve_stream,
    sort_key,
    subtitle_tracks,
)


LK21_BASE_URLS = (
    "https://tv8.lk21official.my",
    "https://layarkaca21.vip",
    "https://lk21official.my",
    "https://tv.lk21official.my",
)

_DETAIL_MARKERS = ("/film/", "/movie/", "/series/", "/tv/", "/watch/", "/detail/")


def _is_detail_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    if any(marker in path for marker in _DETAIL_MARKERS):
        return True
    return bool(re.search(r"/(?:film|movie|series|tv|watch|detail)/[^/]+/?$", path))


def _clean_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"^(?:nonton|download|watch)\s+", "", text, flags=re.I)
    text = re.sub(r"\s+(?:sub\s*indo|subtitle indonesia)\s*$", "", text, flags=re.I)
    text = re.sub(r"\s*\(\d{4}\)\s*$", "", text)
    return text.strip(" -–—|")


class LK21Provider(BaseProvider):
    name = "LK21"
    category = "Flix"
    base_urls = LK21_BASE_URLS

    async def search(self, query: str) -> list[MediaItem]:
        results: list[MediaItem] = []
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=15, follow_redirects=True
        ) as client:
            response, base = await fetch_first(
                client, self.base_urls, "/", params={"s": query}
            )
            if response is None:
                return results

            soup = BeautifulSoup(response.text, "html.parser")
            for widget in soup.select(".sidebar, .widget, #sidebar, .content-right"):
                widget.decompose()

            seen: set[str] = set()
            containers = soup.select(
                "div.ml-item, article.ml-item, article.item, div.movie-item, "
                "div.film-item, article"
            )
            anchors = []
            for container in containers:
                anchor = container.find("a", href=True)
                if anchor:
                    anchors.append((container, anchor))
            if not anchors:
                anchors = [(None, a) for a in soup.find_all("a", href=True)]

            for container, anchor in anchors:
                href = urljoin(base, anchor.get("href", ""))
                if not _is_detail_url(href):
                    continue
                if any(part in href for part in ("/genre/", "/country/", "/year/", "/page/")):
                    continue

                title = anchor.get("title") or ""
                if not title:
                    heading = (container or anchor.parent).find(["h2", "h3", "h4"])
                    title = heading.get_text(" ", strip=True) if heading else anchor.get_text(" ", strip=True)
                title = _clean_title(title)
                if len(title) < 2:
                    continue

                text = (container or anchor.parent).get_text(" ", strip=True)
                year = parse_year(text)
                media_type = (
                    MediaType.SERIES
                    if any(marker in href.lower() or marker in text.lower()
                           for marker in ("/series/", "/tv/", "series", "episode"))
                    else MediaType.MOVIE
                )

                if href in seen:
                    continue
                seen.add(href)
                results.append(
                    MediaItem(
                        id=href,
                        title=title,
                        provider=self.name,
                        media_type=media_type,
                        year=year,
                        category=self.category,
                    )
                )

        return results

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
                )
            ]

        episodes: list[EpisodeItem] = []
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=15, follow_redirects=True
        ) as client:
            try:
                response = await client.get(item.id)
                soup = BeautifulSoup(response.text, "html.parser")
            except Exception:
                return episodes

            seen: set[str] = set()
            for anchor in soup.find_all("a", href=True):
                href = urljoin(item.id, anchor.get("href", ""))
                text = anchor.get_text(" ", strip=True) or anchor.get("title", "")
                haystack = f"{href} {text}".lower()
                if not any(token in haystack for token in ("episode", "/eps/", "-ep-")):
                    continue
                if href in seen or href == item.id:
                    continue
                number = episode_number(haystack) or str(len(episodes) + 1)
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

        if not episodes:
            episodes = [
                EpisodeItem(
                    id=item.id,
                    number="1",
                    title=item.title,
                    season=1,
                    media_title=item.title,
                )
            ]
        return episodes

    async def get_stream(
        self, episode: EpisodeItem, quality: str | None = None
    ) -> StreamInfo:
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=20, follow_redirects=True
        ) as client:
            response = await client.get(episode.id)
            page = response.text
            soup = BeautifulSoup(page, "html.parser")

            page_origin = origin(str(response.url)) or origin(episode.id)
            candidates: list[str] = []
            for tag in soup.find_all(attrs={"data-video": True}):
                value = tag.get("data-video")
                if value:
                    candidates.append(urljoin(str(response.url), value))
            candidates.extend(find_embeds(page, str(response.url)))

            if not candidates:
                direct = find_media_urls(page)
                if direct:
                    return StreamInfo(
                        url=direct[0],
                        title=f"{episode.media_title} - {episode.display_name}",
                        referer=str(response.url),
                        subtitles=subtitle_tracks(find_subtitle_urls(page)),
                        quality=quality,
                    )
                raise RuntimeError(f"No player embed found on: {episode.id}")

            for candidate in candidates:
                stream_url, referer, subs = await resolve_stream(
                    client, candidate, referer=str(response.url)
                )
                if stream_url:
                    return StreamInfo(
                        url=stream_url,
                        title=f"{episode.media_title} - {episode.display_name}",
                        referer=referer or page_origin,
                        subtitles=subs,
                        quality=quality,
                    )

            raise RuntimeError(
                f"Could not resolve a playable stream from: {candidates[0]}"
            )
