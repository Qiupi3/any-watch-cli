from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup
import httpx

from any_watch_core.base import (
    BaseProvider,
    EpisodeItem,
    MediaItem,
    MediaType,
    StreamInfo,
)

BASE_URL = "https://flixhqz.net"
SEARCH_URL = f"{BASE_URL}/search"
AJAX_URL = f"{BASE_URL}/ajax"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


class FlixHQProvider(BaseProvider):
    name = "FlixHQ"
    category = "Movie/Series"

    async def search(self, query: str) -> list[MediaItem]:
        results: list[MediaItem] = []
        async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
            try:
                resp = await client.get(SEARCH_URL, params={"keyword": query})
                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.find_all("div", class_="flw-item")

                # Fallback to slug search if keyword returned empty
                if not items:
                    slug = query.replace(" ", "-")
                    resp = await client.get(f"{SEARCH_URL}/{slug}")
                    soup = BeautifulSoup(resp.text, "html.parser")
                    items = soup.find_all("div", class_="flw-item")

                for item in items[:15]:
                    detail = item.find("div", class_="film-detail")
                    poster = item.find("div", class_="film-poster")
                    a_elem = poster.find("a") if poster else (detail.find("a") if detail else None)
                    if not a_elem:
                        continue

                    href = a_elem.get("href", "")
                    title_elem = detail.find(["h2", "h3"], class_="film-name") if detail else None
                    title = title_elem.get_text(strip=True) if title_elem else (a_elem.get("title") or "Unknown")

                    year = ""
                    media_type = MediaType.MOVIE
                    info_elem = detail.find("div", class_="fd-infor") if detail else None
                    if info_elem:
                        type_span = info_elem.find(class_="fdi-type")
                        t_text = type_span.get_text(strip=True).lower() if type_span else ""
                        if "tv" in t_text or "series" in t_text:
                            media_type = MediaType.SERIES
                        for s in info_elem.find_all("span"):
                            txt = s.get_text(strip=True)
                            if txt.isdigit() and len(txt) == 4:
                                year = txt
                                break

                    full_url = urljoin(BASE_URL, href)
                    results.append(
                        MediaItem(
                            id=full_url,
                            title=title,
                            provider=self.name,
                            media_type=media_type,
                            year=year,
                            category=self.category,
                            extra={"href": href},
                        )
                    )
            except Exception as e:
                print(f"[FlixHQ] Search error: {e}")

        return results

    async def get_episodes(
        self, item: MediaItem, season: int | None = None
    ) -> list[EpisodeItem]:
        episodes: list[EpisodeItem] = []

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

        async with httpx.AsyncClient(headers=HEADERS, timeout=12, follow_redirects=True) as client:
            resp = await client.get(item.id)
            soup = BeautifulSoup(resp.text, "html.parser")

            seasons_dropdown = soup.find("div", class_="slt-seasons-dropdown")
            target_pane_id = None
            season_num = season or 1

            if seasons_dropdown:
                season_items = seasons_dropdown.find_all("a", class_="ss-item")
                seasons_list = []
                for s_item in season_items:
                    pane_id = s_item.get("href", "").lstrip("#")
                    s_title = s_item.get_text(strip=True)
                    m = re.search(r"\d+", s_title)
                    s_idx = int(m.group(0)) if m else len(seasons_list) + 1
                    seasons_list.append({"id": pane_id, "title": s_title, "number": s_idx})

                matched = next((s for s in seasons_list if s["number"] == season_num), None)
                if not matched and seasons_list:
                    matched = seasons_list[0]
                    season_num = matched["number"]

                if matched:
                    target_pane_id = matched["id"]

            pane = soup.find(id=target_pane_id) if target_pane_id else soup.find(class_="tab-pane")
            if pane:
                eps_links = pane.find_all("a", class_="eps-item")
                for a in eps_links:
                    ep_title = a.get("title") or a.get_text(strip=True)
                    ep_url = urljoin(BASE_URL, a.get("href", ""))
                    m = re.search(r"s\d+-e(\d+)", ep_url, re.IGNORECASE) or re.search(
                        r"eps?\s*(\d+)", ep_title, re.IGNORECASE
                    )
                    ep_num = m.group(1) if m else str(len(episodes) + 1)
                    episodes.append(
                        EpisodeItem(
                            id=ep_url,
                            number=ep_num,
                            title=ep_title,
                            season=season_num,
                            media_title=item.title,
                        )
                    )

        return episodes

    async def get_stream(
        self, episode: EpisodeItem, quality: str | None = None
    ) -> StreamInfo:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            page_resp = await client.get(episode.id)
            soup = BeautifulSoup(page_resp.text, "html.parser")

            # Look for video wrapper data-token
            wrapper = (
                soup.find(id="main-wrapper")
                or soup.find(class_="watch_block")
                or soup.find(id="series-player")
                or soup.find(class_="w_b-player")
            )
            token = wrapper.get("data-token") if wrapper else None

            embed_link = None
            if token:
                field_name = "players_show" if episode.season > 0 and episode.title != episode.media_title else "players"
                ajax_res = await client.post(
                    f"{AJAX_URL}/ajax.php",
                    data={field_name: token, "players": token},
                    headers={"Referer": episode.id, "X-Requested-With": "XMLHttpRequest"},
                )
                if ajax_res.status_code == 200:
                    try:
                        servers = ajax_res.json()
                        if isinstance(servers, dict):
                            servers = [servers]
                        if isinstance(servers, list) and servers:
                            chosen = next(
                                (s for s in servers if "vidmoly" in s.get("name", "").lower()),
                                servers[0],
                            )
                            embed_link = chosen.get("link")
                    except Exception:
                        pass

            if not embed_link:
                raise RuntimeError(f"Could not retrieve server embed link for '{episode.title}'")

            # Extract stream and subtitles
            stream_url, subs = await self._extract_stream_and_subs(embed_link, client)
            if not stream_url:
                raise RuntimeError(f"Could not resolve video stream from {embed_link}")

            display_name = (
                f"{episode.media_title} - {episode.display_name}"
                if episode.media_title
                else episode.display_name
            )
            return StreamInfo(
                url=stream_url,
                title=display_name,
                referer=BASE_URL,
                subtitles=subs,
                quality=quality,
            )

    async def _extract_stream_and_subs(
        self, embed_link: str, client: httpx.AsyncClient
    ) -> tuple[str | None, list[str]]:
        video_url = None
        subs_list: list[str] = []

        try:
            parsed = urlparse(embed_link)
            qs = parse_qs(parsed.query)
            sub_urls = qs.get("subget", []) + qs.get("sub.info", [])
            for sub_url in sub_urls:
                try:
                    sub_res = await client.get(sub_url, timeout=6)
                    if sub_res.status_code == 200:
                        tracks = sub_res.json()
                        if isinstance(tracks, list):
                            for track in tracks:
                                if isinstance(track, dict) and "file" in track:
                                    lbl = track.get("label", "").lower()
                                    if "english" in lbl or "eng" in lbl:
                                        subs_list.append(track["file"])
                            if not subs_list and tracks and "file" in tracks[0]:
                                subs_list.append(tracks[0]["file"])
                except Exception:
                    pass
        except Exception:
            pass

        clean_url = embed_link.split("?")[0]
        if clean_url.endswith(".m3u8") or clean_url.endswith(".mp4"):
            video_url = clean_url

        if not video_url:
            for tgt in [embed_link, clean_url]:
                try:
                    res = await client.get(tgt, timeout=8)
                    if res.status_code == 200:
                        m3u8_m = re.search(r"https?://[^\s\"\'\<\>]+\.m3u8[^\s\"\'\<\>]*", res.text)
                        if m3u8_m:
                            video_url = m3u8_m.group(0)
                        if not subs_list:
                            vtts = re.findall(r"https?://[^\s\"\'\<\>]+\.vtt", res.text)
                            for v in vtts:
                                if v not in subs_list:
                                    subs_list.append(v)
                        if video_url:
                            break
                except Exception:
                    continue

        return video_url, subs_list
