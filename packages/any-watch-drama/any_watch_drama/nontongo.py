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
    fetch_first,
    find_embeds,
    find_media_urls,
    find_subtitle_urls,
    parse_year,
    resolve_stream,
    subtitle_tracks,
)


NONTONGO_BASE_URLS = ("https://nontongo.site",)


class NontongoProvider(BaseProvider):
    name = "Nontongo"
    category = "Drama"
    base_urls = NONTONGO_BASE_URLS

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
            for card in soup.select("a.ng-kartu, .ng-kartu[href]"):
                href = urljoin(base, card.get("href", ""))
                if not href.startswith("http") or href in seen:
                    continue

                title_elem = card.select_one(".ng-judul")
                title = (
                    title_elem.get_text(" ", strip=True)
                    if title_elem
                    else card.get("title", "")
                )
                if not title:
                    continue

                year_elem = card.select_one(".ng-sub")
                year = parse_year(year_elem.get_text(strip=True) if year_elem else "")
                type_text = card.select_one(".ng-m-tipe, .ng-b-series, .ng-b-movie")
                type_label = type_text.get_text(" ", strip=True).lower() if type_text else ""
                media_type = (
                    MediaType.SERIES
                    if "serial" in type_label or "series" in type_label
                    else MediaType.MOVIE
                )

                seen.add(href)
                results.append(
                    MediaItem(
                        id=href,
                        title=re.sub(r"\s+", " ", title).strip(),
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
        episodes: list[EpisodeItem] = []
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=15, follow_redirects=True
        ) as client:
            response = await client.get(item.id)
            soup = BeautifulSoup(response.text, "html.parser")

            buttons = soup.select(".ng-eps-t[data-src]")
            if buttons:
                for button in buttons:
                    src = (button.get("data-src") or "").strip()
                    number = button.get_text(strip=True) or str(len(episodes) + 1)
                    if not src:
                        continue
                    episodes.append(
                        EpisodeItem(
                            id=src,
                            number=number,
                            title=f"Episode {number}",
                            season=season or 1,
                            media_title=item.title,
                            extra={"page": item.id},
                        )
                    )
            else:
                player = soup.select_one("#ng-player[data-src], .ng-player[data-src]")
                if player:
                    episodes.append(
                        EpisodeItem(
                            id=(player.get("data-src") or "").strip(),
                            number="1",
                            title=item.title,
                            season=1,
                            media_title=item.title,
                            extra={"page": item.id},
                        )
                    )

        return episodes

    async def get_stream(
        self, episode: EpisodeItem, quality: str | None = None
    ) -> StreamInfo:
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=20, follow_redirects=True
        ) as client:
            page_url = episode.extra.get("page") or episode.id
            referer = page_url
            stream_url, final_referer, subs = await resolve_stream(
                client, episode.id, referer=referer
            )
            if stream_url:
                return StreamInfo(
                    url=stream_url,
                    title=f"{episode.media_title} - {episode.display_name}",
                    referer=final_referer or referer,
                    subtitles=subs,
                    quality=quality,
                )

            # Fallback: the episode page itself may contain a nested player.
            try:
                response = await client.get(page_url)
                for candidate in find_embeds(response.text, str(response.url)):
                    stream_url, final_referer, subs = await resolve_stream(
                        client, candidate, referer=str(response.url)
                    )
                    if stream_url:
                        return StreamInfo(
                            url=stream_url,
                            title=f"{episode.media_title} - {episode.display_name}",
                            referer=final_referer,
                            subtitles=subs,
                            quality=quality,
                        )
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
                "Nontongo player host could not be resolved. Try NaraShika or "
                "KissKH for the same drama."
            )
