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


IDLIX_BASE_URLS = (
    "https://idlix.lat",
    "https://tv2.idlix.link",
    "https://idlix.com",
    "https://idlix.link",
)


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
                client, self.base_urls, "/", params={"s": query}
            )
            if response is None:
                return results

            soup = BeautifulSoup(response.text, "html.parser")
            for widget in soup.select(".sidebar, .widget, #sidebar"):
                widget.decompose()

            seen: set[str] = set()
            blocks = soup.select(".result-item, .movie-item, article.item, article")
            anchors: list[tuple[object, object]] = []
            for block in blocks:
                anchor = block.select_one(
                    ".details .title a, .title a, h2 a, h3 a, a[href]"
                )
                if anchor:
                    anchors.append((block, anchor))
            if not anchors:
                anchors = [(None, a) for a in soup.find_all("a", href=True)]

            for block, anchor in anchors:
                href = urljoin(base, anchor.get("href", ""))
                path = urlparse(href).path.lower()
                if not path or path in ("/", "/movies/", "/tv-shows/"):
                    continue
                if any(part in path for part in ("/genre/", "/country/", "/year/", "/page/")):
                    continue
                if not any(marker in path for marker in ("/movie/", "/tv/", "/series/", "/watch/")):
                    continue

                title = anchor.get_text(" ", strip=True) or anchor.get("title", "")
                if len(title) < 2:
                    continue

                text = (block or anchor.parent).get_text(" ", strip=True)
                year = parse_year(text)
                media_type = (
                    MediaType.SERIES
                    if any(marker in path or marker in text.lower()
                           for marker in ("/tv/", "/series/", "tv series", "episode"))
                    else MediaType.MOVIE
                )

                if href in seen:
                    continue
                seen.add(href)
                results.append(
                    MediaItem(
                        id=href,
                        title=re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip(),
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
            response = await client.get(item.id)
            soup = BeautifulSoup(response.text, "html.parser")

            blocks = soup.select("#seasons .se-c")
            if not blocks:
                blocks = [soup]

            selected_blocks = blocks
            if season is not None:
                matched = []
                for block in blocks:
                    label = block.select_one(".se-q")
                    label_text = label.get_text(" ", strip=True) if label else ""
                    match = re.search(r"(\d+)", label_text)
                    if match and int(match.group(1)) == season:
                        matched.append(block)
                if matched:
                    selected_blocks = matched

            for block in selected_blocks:
                label = block.select_one(".se-q")
                label_text = label.get_text(" ", strip=True) if label else ""
                season_match = re.search(r"(\d+)", label_text)
                season_num = int(season_match.group(1)) if season_match else (season or 1)

                for anchor in block.select(".episodios li a, .episodes li a, li a"):
                    href = anchor.get("href", "")
                    nume = anchor.get("data-nume") or anchor.get("data-episode") or ""
                    post = anchor.get("data-post") or ""
                    etype = anchor.get("data-type") or "episode"
                    text = anchor.get_text(" ", strip=True)
                    number = nume or episode_number(
                        f"{href} {text} {anchor.get('title', '')}"
                    )
                    if not number:
                        continue
                    if not post:
                        post_match = re.search(r"postid-(\d+)", response.text)
                        post = post_match.group(1) if post_match else ""
                    episodes.append(
                        EpisodeItem(
                            id=href or item.id,
                            number=str(number),
                            title=text or f"Episode {number}",
                            season=season_num,
                            media_title=item.title,
                            extra={"post": post, "nume": nume, "type": etype},
                        )
                    )

            episodes.sort(key=lambda ep: (ep.season, sort_key(ep.number)))

        if not episodes:
            post_match = re.search(r"postid-(\d+)", response.text if "response" in locals() else "")
            episodes = [
                EpisodeItem(
                    id=item.id,
                    number="1",
                    title=item.title,
                    season=1,
                    media_title=item.title,
                    extra={"post": post_match.group(1) if post_match else "", "nume": "", "type": "movie"},
                )
            ]
        return episodes

    async def get_stream(
        self, episode: EpisodeItem, quality: str | None = None
    ) -> StreamInfo:
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=20, follow_redirects=True
        ) as client:
            page_url = episode.id if episode.id.startswith("http") else episode.extra.get("page", "")
            response = await client.get(page_url) if page_url else None
            page = response.text if response else ""

            post = episode.extra.get("post") or ""
            nume = episode.extra.get("nume") or ""
            etype = episode.extra.get("type") or "episode"

            if not post and page:
                match = re.search(r"postid-(\d+)", page)
                post = match.group(1) if match else ""

            ajax_origin = origin(page_url or episode.id)
            embed_candidates: list[str] = []
            if post and ajax_origin:
                try:
                    ajax = await client.post(
                        f"{ajax_origin}/wp-admin/admin-ajax.php",
                        data={
                            "action": "doo_player_ajax",
                            "post": post,
                            "nume": nume,
                            "type": etype,
                        },
                        headers={
                            "Referer": page_url or episode.id,
                            "X-Requested-With": "XMLHttpRequest",
                        },
                    )
                    if ajax.status_code == 200:
                        data = json.loads(ajax.text)
                        if isinstance(data, dict):
                            embed = data.get("embed_url") or data.get("link")
                            if embed:
                                embed_candidates.append(urljoin(page_url or episode.id, embed))
                except Exception:
                    pass

            if page:
                embed_candidates.extend(find_embeds(page, page_url or episode.id))

            if page and not embed_candidates:
                direct = find_media_urls(page)
                if direct:
                    return StreamInfo(
                        url=direct[0],
                        title=f"{episode.media_title} - {episode.display_name}",
                        referer=page_url or episode.id,
                        subtitles=subtitle_tracks(find_subtitle_urls(page)),
                        quality=quality,
                    )

            for candidate in embed_candidates:
                stream_url, referer, subs = await resolve_stream(
                    client,
                    candidate,
                    referer=page_url or episode.id,
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
                "IDLIX player did not return a stream. The mirror may be blocking "
                "this request; retry with another IDLIX domain or use LK21."
            )
