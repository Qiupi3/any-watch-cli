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


SAMEHADAKU_BASE_URLS = (
    "https://v2.samehadaku.how",
    "https://samehadaku.care",
    "https://samehadaku.email",
    "https://v1.samehadaku.how",
)


class SamehadakuProvider(BaseProvider):
    name = "Samehadaku"
    category = "Anime"
    base_urls = SAMEHADAKU_BASE_URLS

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
            blocks = soup.select(".animpost, .listupd article, article.bs, article")

            for block in blocks:
                anchor = block.select_one(
                    "h2 a, h3 a, .data h2 a, .tt h2 a, a[href*='/anime/'], a[href]"
                )
                if not anchor:
                    continue
                href = urljoin(base, anchor.get("href", ""))
                if "/anime/" not in href:
                    continue
                title_tag = block.select_one(".tt h2, .data h2, h2, h3")
                title = (
                    title_tag.get_text(" ", strip=True)
                    if title_tag
                    else anchor.get_text(" ", strip=True)
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
                        year=parse_year(block.get_text(" ", strip=True)),
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
            selectors = (
                ".eplister ul li a",
                ".lstepsiode ul li a",
                ".episodelist ul li a",
                ".episodelist a[href]",
            )
            anchors = []
            for selector in selectors:
                found = soup.select(selector)
                if found:
                    anchors = found
                    break

            if not anchors:
                # Current theme: one row per episode with a number link and a
                # longer title link. Pick the title link, not the number badge.
                rows = soup.select("div.flex.items-center.gap-3")
                for row in rows:
                    links = [
                        link
                        for link in row.select("a[href]")
                        if any(
                            token in (link.get("href") or "").lower()
                            for token in ("/episode/", "-episode-", "/eps/")
                        )
                    ]
                    if links:
                        anchors.append(
                            max(
                                links,
                                key=lambda link: len(link.get_text(" ", strip=True)),
                            )
                        )

            if not anchors:
                anchors = [
                    anchor
                    for anchor in soup.find_all("a", href=True)
                    if any(token in (anchor.get("href") or "").lower()
                           for token in ("/episode/", "-episode-", "/eps/"))
                ]

            for anchor in anchors:
                href = urljoin(item.id, anchor.get("href", ""))
                text = anchor.get_text(" ", strip=True)
                haystack = f"{href} {text}".lower()
                if href in seen or "batch" in haystack or "download" in haystack:
                    continue
                number = (
                    anchor.select_one(".epl-num")
                    and anchor.select_one(".epl-num").get_text(strip=True)
                ) or episode_number(f"{href} {text}")
                if not number:
                    number = str(len(episodes) + 1)
                seen.add(href)
                episodes.append(
                    EpisodeItem(
                        id=href,
                        number=str(number),
                        title=text or f"Episode {number}",
                        season=season or 1,
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
            for selector in ("#pembed iframe", ".player-embed iframe", ".player iframe", "iframe"):
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
                "Samehadaku player could not be resolved. The mirror domain may "
                "be blocked; try OtakuDesu or AnoBoy."
            )
