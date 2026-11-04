from __future__ import annotations

import re
from urllib.parse import urljoin, urlparse, urlunparse

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
    resolve_playable_url,
    resolve_stream,
    sort_key,
    subtitle_tracks,
)


def _series_name(text: str) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    text = re.sub(r"\s+episode\s+\d+.*$", "", text, flags=re.I)
    for _ in range(3):
        text = re.sub(
            r"^(?:permalink\s+ke:|nonton|download|watch)\s*",
            "",
            text,
            flags=re.I,
        )
        text = re.sub(
            r"\s+(?:sub(?:title)?\s*indo(?:nesia)?|subtitle)\s*$",
            "",
            text,
            flags=re.I,
        )
    return text.strip(" -–—|")


def _article_title(article, anchor) -> str:
    heading = article.select_one(".entry-title, h2.entry-title, h2, h3")
    title = heading.get_text(" ", strip=True) if heading else ""
    if not title and anchor is not None:
        title = anchor.get_text(" ", strip=True) or anchor.get("title", "")
    if not title:
        image = article.select_one("img[alt], img[title]")
        if image:
            title = image.get("alt") or image.get("title") or ""
    return title


def _align_mirror(url: str, base: str) -> str:
    """Keep same-site links on the mirror that actually answered the request."""
    parsed = urlparse(url)
    base_parsed = urlparse(base)
    if not parsed.netloc or not base_parsed.netloc:
        return url
    if parsed.netloc != base_parsed.netloc and (
        parsed.netloc.endswith(f".{base_parsed.netloc}")
        or base_parsed.netloc.endswith(f".{parsed.netloc}")
    ):
        return urlunparse(
            (
                base_parsed.scheme,
                base_parsed.netloc,
                parsed.path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )
    return url


class GmrThemeProvider(BaseProvider):
    """Scraper for GMR/idmuvi-style WordPress drama themes."""

    category = "Drama"
    episode_path_markers: tuple[str, ...] = ("/eps/", "/episode/", "?player=", "/episode-")

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
            for article in soup.select("article.item, .gmr-box-archive, article"):
                anchor = (
                    article.select_one(".entry-title a, h2 a, h3 a")
                    or article.select_one("a[itemprop='url']")
                    or article.select_one("a[href]")
                )
                if not anchor:
                    continue
                href = urljoin(base, anchor.get("href", ""))
                href = _align_mirror(href, base)
                if not href.startswith("http") or href in seen:
                    continue
                low_href = href.lower()
                if any(
                    marker in low_href
                    for marker in ("/eps/", "/episode/", "/episode-", "?player=")
                ):
                    continue

                raw_title = _article_title(article, anchor)
                series = _series_name(raw_title)
                if len(series) < 2:
                    continue

                year = parse_year(raw_title)
                if not year:
                    image = article.select_one("img[title], img[alt]")
                    hint = ""
                    if image:
                        hint = f"{image.get('title', '')} {image.get('alt', '')}"
                    year = parse_year(hint)

                seen.add(href)
                results.append(
                    MediaItem(
                        id=href,
                        title=series,
                        provider=self.name,
                        media_type=MediaType.DRAMA,
                        year=year,
                        category=self.category,
                        extra={"raw_title": raw_title},
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

            def normalize(value: str) -> str:
                value = str(value or "").strip()
                return re.sub(r"^0+(?=\d)", "", value)

            series_anchors = list(soup.select(".gmr-listseries a[href]"))
            pagination = soup.select(".page-links a.post-page-numbers[href]")

            if series_anchors:
                anchors = series_anchors
            elif pagination:
                # Paginated series (DramaSerial): page 1 is the series URL and
                # each further page is one episode.
                page_map: dict[str, str] = {"1": item.id}
                for anchor in pagination:
                    href = urljoin(item.id, anchor.get("href", ""))
                    href = _align_mirror(href, item.id)
                    number = normalize(anchor.get_text(" ", strip=True))
                    if not number.isdigit():
                        number = normalize(episode_number(href) or "")
                    if number:
                        page_map[number] = href

                for number, href in sorted(
                    page_map.items(), key=lambda pair: sort_key(pair[0])
                ):
                    episodes.append(
                        EpisodeItem(
                            id=href,
                            number=number,
                            title=f"Episode {number}",
                            season=season or 1,
                            media_title=item.title,
                        )
                    )
                anchors = []
            else:
                anchors = [
                    anchor
                    for anchor in soup.find_all("a", href=True)
                    if any(marker in (anchor.get("href") or "").lower()
                           for marker in self.episode_path_markers)
                ]

            seen: set[str] = set()
            for anchor in anchors:
                href = urljoin(item.id, anchor.get("href", ""))
                href = _align_mirror(href, item.id)
                classes = anchor.get("class") or []
                if "gmr-all-serie" in classes:
                    continue
                text = anchor.get_text(" ", strip=True) or anchor.get("title", "")
                number = normalize(episode_number(f"{text} {href}") or "")
                if not number:
                    continue
                season_match = re.search(r"s(\d+)", text, re.I)
                season_num = int(season_match.group(1)) if season_match else (season or 1)
                if season is not None and season_num != season:
                    continue
                if href in seen:
                    continue
                seen.add(href)
                episodes.append(
                    EpisodeItem(
                        id=href,
                        number=number,
                        title=text or f"Episode {number}",
                        season=season_num,
                        media_title=item.title,
                    )
                )

            episodes.sort(key=lambda ep: (ep.season, sort_key(ep.number)))

        if not episodes:
            episodes = [
                EpisodeItem(
                    id=item.id,
                    number="1",
                    title=item.extra.get("raw_title") or item.title,
                    season=season or 1,
                    media_title=item.title,
                )
            ]
        return episodes

    async def _fallback_stream(
        self, episode: EpisodeItem, quality: str | None = None
    ) -> StreamInfo:
        """Use Nontongo when this site only links to dead file hosts."""
        from difflib import SequenceMatcher


        query = re.sub(r"\s*\(\d{4}\)\s*$", "", episode.media_title).strip()
        query = re.sub(
            r"\s+(?:sub(?:title)?\s*indo(?:nesia)?|eps?\s*\d+.*)$",
            "",
            query,
            flags=re.I,
        ).strip()

        provider = NontongoProvider()
        items = await provider.search(query)
        if not items and query != episode.media_title:
            items = await provider.search(episode.media_title)
        if not items:
            raise RuntimeError(
                f"{self.name} only links to defunct file hosts and no fallback "
                "source was found. Try another drama site."
            )

        wanted = re.sub(r"[^a-z0-9]+", "", query.lower())
        best = max(
            items,
            key=lambda item: SequenceMatcher(
                None,
                wanted,
                re.sub(r"[^a-z0-9]+", "", item.title.lower()),
            ).ratio(),
        )
        episodes = await provider.get_episodes(best)
        target = next(
            (ep for ep in episodes if str(ep.number) == str(episode.number)),
            episodes[0],
        )
        stream = await provider.get_stream(target, quality)
        stream.title = (
            f"{episode.media_title} - {episode.display_name} "
            f"(via {provider.name})"
        )
        stream.extra["fallback"] = provider.name
        return stream

    async def get_stream(
        self, episode: EpisodeItem, quality: str | None = None
    ) -> StreamInfo:
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=20, follow_redirects=True
        ) as client:
            response = await client.get(episode.id)
            page = response.text
            candidates = find_embeds(page, str(response.url))

            for candidate in candidates:
                stream_url, referer, subs = await resolve_stream(
                    client, candidate, referer=str(response.url)
                )
                if not stream_url:
                    continue
                final_url = await resolve_playable_url(
                    client, stream_url, referer=referer or str(response.url)
                )
                if not final_url:
                    continue
                return StreamInfo(
                    url=final_url,
                    title=f"{episode.media_title} - {episode.display_name}",
                    referer=referer,
                    subtitles=subs,
                    quality=quality,
                )

            direct = find_media_urls(page)
            for media_url in direct:
                final_url = await resolve_playable_url(
                    client, media_url, referer=str(response.url)
                )
                if not final_url:
                    continue
                return StreamInfo(
                    url=final_url,
                    title=f"{episode.media_title} - {episode.display_name}",
                    referer=str(response.url),
                    subtitles=subtitle_tracks(find_subtitle_urls(page)),
                    quality=quality,
                )

            raise RuntimeError(
                f"{self.name} episode has no resolvable player. The host may be "
                "down or geo-blocked; try another drama site."
            )
