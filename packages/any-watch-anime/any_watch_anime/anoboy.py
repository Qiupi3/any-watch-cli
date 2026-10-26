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


ANOBOY_BASE_URLS = ("https://anoboy.quest", "https://anoboy.live")

_GENERIC_CATEGORIES = {
    "anime",
    "donghua",
    "anime-movie",
    "tokusatsu",
    "live-action",
    "live-action-movie",
    "studio-ghibli",
    "rekomended",
    "uncategorized",
}


def _series_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"\s*\[download\].*$", "", text, flags=re.I)
    text = re.sub(r"\s+episode\s+\d+.*$", "", text, flags=re.I)
    text = re.sub(r"\s+(?:selesai|tamat)\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+sub(?:title)?\s*indo(?:nesia)?\s*$", "", text, flags=re.I)
    return text.strip(" -–—|")


def _post_link(post) -> tuple[str, str]:
    """Return (href, title) for an AnoBoy post.

    The theme wraps each ``div.amv`` block in an anchor, so the link is not a
    child of the ``div.post`` marker.
    """
    anchor = post.find_parent("a", href=True)
    scope = post.parent or post
    if anchor is None:
        anchor = scope.select_one("h2 a, h3 a, .ibox1 a")
    title_tag = scope.select_one(".ibox1") if scope is not post else None
    if title_tag is None:
        title_tag = post.select_one(".ibox1")
    href = anchor.get("href", "") if anchor else ""
    title = ""
    if title_tag is not None:
        title = title_tag.get_text(" ", strip=True)
    if not title and anchor is not None:
        title = anchor.get("title", "") or anchor.get_text(" ", strip=True)
    return href, title


class AnoBoyProvider(BaseProvider):
    name = "AnoBoy"
    category = "Anime"
    base_urls = ANOBOY_BASE_URLS

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
            container = soup.select_one(".column-content") or soup
            posts = container.select("div.post")
            seen: set[str] = set()

            for post in posts:
                raw_href, raw_title = _post_link(post)
                if not raw_href or not raw_title:
                    continue
                href = urljoin(base, raw_href)

                category_slug = ""
                for class_name in post.get("class", []):
                    if not class_name.startswith("category-"):
                        continue
                    slug = class_name[len("category-"):]
                    if slug.lower() in _GENERIC_CATEGORIES:
                        continue
                    if len(slug) > len(category_slug):
                        category_slug = slug

                if category_slug:
                    item_id = f"{base}/category/{category_slug}/"
                else:
                    item_id = href

                series = _series_title(raw_title)
                if not series or item_id in seen:
                    continue
                seen.add(item_id)

                season_match = re.search(r"season\s*(\d+)", series, re.I)
                results.append(
                    MediaItem(
                        id=item_id,
                        title=series,
                        provider=self.name,
                        media_type=MediaType.ANIME,
                        year=parse_year(raw_title),
                        category=self.category,
                        extra={
                            "category_slug": category_slug,
                            "post_url": href,
                            "season": season_match.group(1) if season_match else "",
                        },
                    )
                )

        return results

    async def get_episodes(
        self, item: MediaItem, season: int | None = None
    ) -> list[EpisodeItem]:
        episodes: list[EpisodeItem] = []
        season_num = season or int(item.extra.get("season") or 1)

        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=15, follow_redirects=True
        ) as client:
            response = await client.get(item.id)
            soup = BeautifulSoup(response.text, "html.parser")
            posts = soup.select("div.post")
            seen: set[str] = set()

            for post in posts:
                raw_href, title = _post_link(post)
                if not raw_href:
                    continue
                href = urljoin(item.id, raw_href)
                haystack = f"{href} {title}".lower()
                if "episode" not in haystack or "download" in haystack:
                    continue
                if href in seen or href == item.id:
                    continue
                number = episode_number(haystack) or str(len(episodes) + 1)
                seen.add(href)
                episodes.append(
                    EpisodeItem(
                        id=href,
                        number=number,
                        title=title or f"Episode {number}",
                        season=season_num,
                        media_title=item.title,
                    )
                )

            episodes.sort(key=lambda ep: sort_key(ep.number))

        if not episodes:
            fallback = item.extra.get("post_url")
            if fallback:
                episodes = [
                    EpisodeItem(
                        id=fallback,
                        number="1",
                        title=item.title,
                        season=season_num,
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
            candidates = find_embeds(page, str(response.url))

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
                raise RuntimeError(f"No video player found on: {episode.id}")

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

            raise RuntimeError(
                "AnoBoy player chain could not be resolved (Blogger token may "
                "have expired). Try another episode or mirror."
            )
