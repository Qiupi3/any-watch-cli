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
    origin,
    parse_year,
    resolve_stream,
    sort_key,
    subtitle_tracks,
)


OTAKUDESU_BASE_URLS = (
    "https://otakudesu.cloud",
    "https://otakudesu.camera",
    "https://otakudesu.best",
    "https://otakudesu.love",
)


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
            for anchor in soup.select(
                ".episodelist ul li a, .episodelist a[href], "
                ".infozingle ~ .episodelist a[href]"
            ):
                href = urljoin(item.id, anchor.get("href", ""))
                text = anchor.get_text(" ", strip=True)
                if href in seen:
                    continue
                if "batch" in text.lower() or "download" in text.lower():
                    continue
                number = episode_number(f"{href} {text}")
                if not number:
                    match = re.search(r"episode[- ]?(\d+)", href, re.I)
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

    async def get_stream(
        self, episode: EpisodeItem, quality: str | None = None
    ) -> StreamInfo:
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=20, follow_redirects=True
        ) as client:
            response = await client.get(episode.id)
            page = response.text
            soup = BeautifulSoup(page, "html.parser")
            page_origin = origin(str(response.url))

            mirror_ids: list[str] = []
            for anchor in soup.select(".mirrorstream ul li a, .mirrorstream a, a[data-content]"):
                data_content = anchor.get("data-content")
                if data_content:
                    mirror_ids.append(data_content)

            embed_candidates: list[str] = []
            if mirror_ids and page_origin:
                for mirror_id in mirror_ids:
                    try:
                        ajax = await client.post(
                            f"{page_origin}/wp-admin/admin-ajax.php",
                            data={"action": "player", "id": mirror_id},
                            headers={
                                "Referer": str(response.url),
                                "X-Requested-With": "XMLHttpRequest",
                            },
                        )
                        if ajax.status_code != 200:
                            continue
                        player_soup = BeautifulSoup(ajax.text, "html.parser")
                        for tag in player_soup.find_all("iframe"):
                            src = tag.get("src")
                            if src:
                                embed_candidates.append(
                                    urljoin(str(response.url), src.strip())
                                )
                        if not embed_candidates:
                            embed_candidates.extend(
                                find_embeds(ajax.text, str(response.url))
                            )
                        if embed_candidates:
                            break
                    except Exception:
                        continue

            embed_candidates.extend(
                embed for embed in find_embeds(page, str(response.url))
                if embed not in embed_candidates
            )

            for candidate in embed_candidates:
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
                "OtakuDesu mirror AJAX returned no playable embed. Try another "
                "server by re-running, or use Samehadaku/AnoBoy."
            )
