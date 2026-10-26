from __future__ import annotations

import re
from urllib.parse import urljoin

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
    find_media_urls,
    find_subtitle_urls,
    parse_year,
    resolve_stream,
    sort_key,
    subtitle_tracks,
)


DRAKORINDO_BASE_URLS = (
    "https://drakorindo.autos",
    "https://drakorindo.win",
)


def _clean_drama_title(text: str) -> str:
    title = re.sub(r"\s+", " ", text or "").strip()
    title = re.sub(r"^download\s+", "", title, flags=re.I)
    title = re.sub(r"^drama\s+(?:korea|china|jepang|japan|thailand|asia)\s+", "", title, flags=re.I)
    title = re.sub(r"\s+sub(?:title)?\s*indo(?:nesia)?\s*$", "", title, flags=re.I)
    title = re.sub(r"\s*\(\d{4}\)\s*$", "", title)
    return title.strip(" -–—|")


def _quality_rank(text: str) -> int:
    match = re.search(r"(1080|720|480|360)", text or "")
    return int(match.group(1)) if match else 0


class DrakorindoProvider(BaseProvider):
    name = "Drakorindo"
    category = "Drama"
    base_urls = DRAKORINDO_BASE_URLS

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
            seen: set[str] = set()
            for article in soup.select("article.mh-loop-item, .mh-loop-item, article"):
                anchor = article.select_one(".entry-title a, h2 a, h3 a")
                if not anchor:
                    continue
                href = urljoin(base, anchor.get("href", ""))
                title = _clean_drama_title(anchor.get_text(" ", strip=True))
                if len(title) < 2 or href in seen:
                    continue
                seen.add(href)
                results.append(
                    MediaItem(
                        id=href,
                        title=title,
                        provider=self.name,
                        media_type=MediaType.DRAMA,
                        year=parse_year(article.get_text(" ", strip=True)),
                        category=self.category,
                    )
                )

        return results

    async def get_episodes(
        self, item: MediaItem, season: int | None = None
    ) -> list[EpisodeItem]:
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=15, follow_redirects=True
        ) as client:
            response = await client.get(item.id)
            soup = BeautifulSoup(response.text, "html.parser")

            sources: dict[str, list[tuple[int, str]]] = {}
            for anchor in soup.find_all("a", href=True):
                href = urljoin(item.id, anchor.get("href", ""))
                low = href.lower()
                if not any(host in low for host in ("filemoon.", "filemoon.to", "streamwish", "dood.", "vidhide")):
                    continue
                number = episode_number(href)
                if not number:
                    match = re.search(r"(?:episode|eps?)[\s_.-]*(\d+)", href, re.I)
                    number = match.group(1) if match else ""
                if not number:
                    continue
                rank = _quality_rank(href) or _quality_rank(anchor.get_text(" ", strip=True))
                sources.setdefault(number, []).append((rank, href))

            episodes: list[EpisodeItem] = []
            for number in sorted(sources, key=sort_key):
                links = [url for _rank, url in sorted(sources[number], reverse=True)]
                episodes.append(
                    EpisodeItem(
                        id=links[0],
                        number=number,
                        title=f"Episode {number}",
                        season=season or 1,
                        media_title=item.title,
                        extra={"page": item.id, "sources": links},
                    )
                )

            if not episodes:
                episodes = [
                    EpisodeItem(
                        id=item.id,
                        number="1",
                        title=item.title,
                        season=season or 1,
                        media_title=item.title,
                        extra={"page": item.id, "sources": []},
                    )
                ]

        return episodes

    async def get_stream(
        self, episode: EpisodeItem, quality: str | None = None
    ) -> StreamInfo:
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=20, follow_redirects=True
        ) as client:
            page = episode.extra.get("page") or episode.id
            sources = list(episode.extra.get("sources") or [])
            if episode.id not in sources:
                sources.insert(0, episode.id)

            for source in sources:
                stream_url, referer, subs = await resolve_stream(
                    client, source, referer=page
                )
                if stream_url:
                    return StreamInfo(
                        url=stream_url,
                        title=f"{episode.media_title} - {episode.display_name}",
                        referer=referer or page,
                        subtitles=subs,
                        quality=quality,
                    )

            # Last resort: page-level player/subtitle links.
            try:
                response = await client.get(page)
                direct = find_media_urls(response.text)
                if direct:
                    return StreamInfo(
                        url=direct[0],
                        title=f"{episode.media_title} - {episode.display_name}",
                        referer=str(response.url),
                        subtitles=subtitle_tracks(find_subtitle_urls(response.text)),
                        quality=quality,
                    )
            except Exception:
                pass

            raise RuntimeError(
                "Drakorindo only exposes file-host links for this episode and the "
                "host did not return a playable stream. Try NaraShika/KissKH."
            )
