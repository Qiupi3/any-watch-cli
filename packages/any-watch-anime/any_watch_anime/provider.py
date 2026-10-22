from __future__ import annotations

import base64
import json
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

BASE_URL = "https://hianime.at"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}
XOR_KEY = b"otaku-embed-v1"


class HiAnimeProvider(BaseProvider):
    name = "HiAnime"
    category = "Anime"

    async def search(self, query: str) -> list[MediaItem]:
        results: list[MediaItem] = []
        async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
            try:
                resp = await client.get(f"{BASE_URL}/search", params={"keyword": query})
                soup = BeautifulSoup(resp.text, "html.parser")
                items = soup.select(".film-detail")

                for it in items[:15]:
                    a_elem = it.select_one(".film-name a")
                    if not a_elem:
                        continue

                    title = a_elem.get("title") or a_elem.get_text(strip=True)
                    href = a_elem.get("href", "")
                    full_url = urljoin(BASE_URL, href)
                    slug = href.lstrip("/")

                    # Extract anime_id from trailing digits of slug (e.g. solo-leveling-235 -> 235)
                    anime_id = ""
                    m = re.search(r"-(\d+)$", slug)
                    if m:
                        anime_id = m.group(1)

                    # Extract year
                    year = ""
                    for span in it.select(".fd-infor .fdi-item"):
                        txt = span.get_text(strip=True)
                        if txt.isdigit() and len(txt) == 4:
                            year = txt
                            break

                    results.append(
                        MediaItem(
                            id=full_url,
                            title=title,
                            provider=self.name,
                            media_type=MediaType.ANIME,
                            year=year,
                            category=self.category,
                            extra={"anime_id": anime_id, "slug": slug},
                        )
                    )
            except Exception as e:
                print(f"[HiAnime] Search error: {e}")

        return results

    async def get_episodes(
        self, item: MediaItem, season: int | None = None
    ) -> list[EpisodeItem]:
        episodes: list[EpisodeItem] = []
        anime_id = item.extra.get("anime_id")
        if not anime_id:
            m = re.search(r"-(\d+)$", item.id.rstrip("/"))
            anime_id = m.group(1) if m else None

        if not anime_id:
            return episodes

        async with httpx.AsyncClient(headers=HEADERS, timeout=12, follow_redirects=True) as client:
            resp = await client.get(f"{BASE_URL}/api/theme/episode/list/{anime_id}")
            if resp.status_code == 200:
                data = resp.json()
                html_snippet = data.get("html", "")
                soup = BeautifulSoup(html_snippet, "html.parser")

                for ep in soup.select(".ep-item"):
                    ep_data_id = ep.get("data-id")
                    ep_num = ep.get("data-number") or str(len(episodes) + 1)
                    ep_title = ep.get("title") or f"Episode {ep_num}"
                    episodes.append(
                        EpisodeItem(
                            id=ep_data_id,
                            number=ep_num,
                            title=ep_title,
                            season=1,
                            media_title=item.title,
                            extra={"anime_id": anime_id},
                        )
                    )

        return episodes

    async def get_stream(
        self, episode: EpisodeItem, quality: str | None = None
    ) -> StreamInfo:
        async with httpx.AsyncClient(headers=HEADERS, timeout=15, follow_redirects=True) as client:
            srv_resp = await client.get(
                f"{BASE_URL}/api/theme/episode/servers",
                params={"episodeId": episode.id},
            )
            if srv_resp.status_code != 200:
                raise RuntimeError(f"Failed to fetch servers for episode {episode.number}")

            soup = BeautifulSoup(srv_resp.json().get("html", ""), "html.parser")
            servers = soup.select(".server-item")

            # Look for ZokoAnime sub server (or fallback to dub)
            chosen_server = next(
                (s for s in servers if s.get("data-server-name") == "ZokoAnime" and s.get("data-type") == "sub"),
                None,
            )
            if not chosen_server:
                chosen_server = next(
                    (s for s in servers if s.get("data-server-name") == "ZokoAnime"),
                    None,
                )

            if not chosen_server or not chosen_server.get("data-hash"):
                raise RuntimeError("ZokoAnime server not found for this episode")

            s_hash = chosen_server.get("data-hash")
            embed_url = base64.b64decode(s_hash).decode("utf-8")

            # Fetch embed page to extract encrypted payload
            embed_resp = await client.get(embed_url, headers={"Referer": f"{BASE_URL}/"})
            blob_match = re.search(r'window\.__P\s*=\s*\"([^\"]+)\"', embed_resp.text)
            if not blob_match:
                raise RuntimeError("Failed to extract player payload from embed")

            blob = blob_match.group(1)
            raw = base64.b64decode(blob)
            dec = bytes([b ^ XOR_KEY[i % len(XOR_KEY)] for i, b in enumerate(raw)])
            dec_json = json.loads(dec.decode("utf-8"))

            m3u8_url = dec_json.get("src")
            if not m3u8_url:
                raise RuntimeError("No streaming source found in decrypted player payload")

            subs = []
            for track in dec_json.get("subtitles", []):
                src = track.get("src")
                if src:
                    if track.get("default"):
                        subs.insert(0, src)
                    else:
                        subs.append(src)

            referer = re.match(r"^(https?://[^/]+)", embed_url).group(1) + "/"
            display_name = f"{episode.media_title} - {episode.display_name}"

            return StreamInfo(
                url=m3u8_url,
                title=display_name,
                referer=referer,
                subtitles=subs,
                quality=quality,
            )
