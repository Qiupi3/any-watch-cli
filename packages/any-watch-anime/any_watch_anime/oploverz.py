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
    find_embeds,
    find_media_urls,
    find_subtitle_urls,
    parse_year,
    resolve_stream,
    sort_key,
    subtitle_tracks,
)


OPLOVERZ_BASE_URLS = (
    "https://oploverz.ch",
    "https://oploverz.co.in",
    "https://link.oploverz.ltd",
)


class OploverzProvider(BaseProvider):
    name = "Oploverz"
    category = "Anime"
    base_urls = OPLOVERZ_BASE_URLS

    @staticmethod
    def _next_page(soup: BeautifulSoup, current_url: str) -> str | None:
        anchor = soup.select_one(
            ".ds-an-episode-pagination a.next, .pagination a.next"
        )
        if not anchor:
            return None
        href = anchor.get("href")
        if not href:
            return None
        return urljoin(current_url, href)

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
            for article in soup.select(".listupd article, article.bs, .bsx"):
                anchor = article.select_one("a.tip, a[href*='/series/'], a[href]")
                if not anchor:
                    continue
                href = urljoin(base, anchor.get("href", ""))
                if "/series/" not in href:
                    continue
                title = (
                    anchor.get("title")
                    or article.select_one(".tt h2, h2")
                    and article.select_one(".tt h2, h2").get_text(" ", strip=True)
                    or anchor.get_text(" ", strip=True)
                )
                title = re.sub(r"\s+", " ", title or "").strip()
                if not title or href in seen:
                    continue
                seen.add(href)
                results.append(
                    MediaItem(
                        id=href,
                        title=title,
                        provider=self.name,
                        media_type=MediaType.ANIME,
                        year=parse_year(article.get_text(" ", strip=True)),
                        category=self.category,
                    )
                )

        return results

    async def get_episodes(
        self, item: MediaItem, season: int | None = None
    ) -> list[EpisodeItem]:
        episodes: list[EpisodeItem] = []
        season_num = season or 1

        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=15, follow_redirects=True
        ) as client:
            response = await client.get(item.id)
            pages = [response.text]
            soup = BeautifulSoup(response.text, "html.parser")

            # Long-running series split their episode list over ?ep_page=N.
            # Follow the "next" link instead of the numbered links, since the
            # paginator only renders a truncated window of page numbers.
            next_url = self._next_page(soup, str(response.url))
            visited: set[str] = set()
            while next_url and next_url not in visited and len(pages) < 40:
                visited.add(next_url)
                try:
                    page_response = await client.get(next_url)
                except httpx.HTTPError:
                    break
                if page_response.status_code != 200:
                    break
                pages.append(page_response.text)
                next_url = self._next_page(
                    BeautifulSoup(page_response.text, "html.parser"), next_url
                )

            seen: set[str] = set()
            for page_html in pages:
                page_soup = BeautifulSoup(page_html, "html.parser")
                for anchor in page_soup.select(
                    ".eplister ul li a[href], .eplister a[href]"
                ):
                    href = urljoin(item.id, anchor.get("href", ""))
                    if href in seen:
                        continue
                    number_tag = anchor.select_one(".epl-num")
                    number = (
                        number_tag.get_text(strip=True) if number_tag else None
                    ) or episode_number(f"{href} {anchor.get_text(' ', strip=True)}")
                    if not number:
                        continue
                    title_tag = anchor.select_one(".epl-title")
                    title = (
                        title_tag.get_text(" ", strip=True) if title_tag else ""
                    ) or anchor.get_text(" ", strip=True)
                    title = re.sub(r"\s+", " ", title).strip()
                    seen.add(href)
                    episodes.append(
                        EpisodeItem(
                            id=href,
                            number=str(number),
                            title=title or f"Episode {number}",
                            season=season_num,
                            media_title=item.title,
                        )
                    )

            episodes.sort(key=lambda ep: sort_key(ep.number))

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

            candidates: list[str] = []
            for selector in ("#pembed iframe", ".player-embed iframe", "iframe"):
                for tag in soup.select(selector):
                    src = tag.get("src") or tag.get("data-src")
                    if src:
                        candidate = urljoin(str(response.url), src.strip())
                        if candidate not in candidates:
                            candidates.append(candidate)
                if candidates:
                    break
            candidates.extend(
                embed for embed in find_embeds(page, str(response.url))
                if embed not in candidates
            )

            for candidate in candidates:
                stream_url, referer, subs = await resolve_stream(
                    client, candidate, referer=str(response.url)
                )
                if stream_url:
                    return StreamInfo(
                        url=stream_url,
                        title=f"{episode.media_title} - {episode.display_name}",
                        referer=referer,
                        subtitles=subs,
                        quality=quality,
                    )

            direct = find_media_urls(page)
            if direct:
                return StreamInfo(
                    url=direct[0],
                    title=f"{episode.media_title} - {episode.display_name}",
                    referer=str(response.url),
                    subtitles=subtitle_tracks(find_subtitle_urls(page)),
                    quality=quality,
                )

            raise RuntimeError(
                "Oploverz player could not be resolved. The StreamWish/Asnwish "
                "embed may be expired or geo-blocked."
            )
