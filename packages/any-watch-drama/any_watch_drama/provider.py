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

DRAMACOOL_BASE = "https://wxx.dramacool.com.tr"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
}


class DramaProvider(BaseProvider):
    name = "DramaCool"
    category = "Drama"

    async def search(self, query: str) -> list[MediaItem]:
        """Search DramaCool index for Korean, Chinese, and Asian dramas."""
        results: list[MediaItem] = []
        async with httpx.AsyncClient(headers=HEADERS, timeout=10, follow_redirects=True) as client:
            try:
                resp = await client.get(f"{DRAMACOOL_BASE}/", params={"s": query})
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for a in soup.find_all("a"):
                        href = a.get("href", "")
                        if "drama-detail" in href:
                            h_elem = a.find(["h2", "h3", "h4"])
                            title = h_elem.get_text(strip=True) if h_elem else a.get_text(strip=True)
                            if not title or len(title) < 2:
                                continue

                            year = ""
                            m = re.search(r"\((\d{4})\)", title)
                            if m:
                                year = m.group(1)

                            clean_title = re.sub(r"\(\d{4}\)", "", title).strip()

                            # Avoid duplicate entries
                            if not any(r.id == href for r in results):
                                results.append(
                                    MediaItem(
                                        id=href,
                                        title=clean_title,
                                        provider=self.name,
                                        media_type=MediaType.DRAMA,
                                        year=year,
                                        category=self.category,
                                        extra={"raw_title": title},
                                    )
                                )
            except Exception as e:
                print(f"[DramaCool] Search error: {e}")

        return results

    async def get_episodes(
        self, item: MediaItem, season: int | None = None
    ) -> list[EpisodeItem]:
        """Fetch all available episodes from the drama detail page."""
        episodes: list[EpisodeItem] = []
        async with httpx.AsyncClient(headers=HEADERS, timeout=12, follow_redirects=True) as client:
            try:
                resp = await client.get(item.id)
                soup = BeautifulSoup(resp.text, "html.parser")
                found_links = []
                for a in soup.find_all("a", href=True):
                    href = a.get("href", "")
                    if "-episode-" in href:
                        ep_text = a.get_text(strip=True)
                        found_links.append((ep_text, href))

                # Deduplicate links preserving order
                seen_urls = set()
                for ep_text, href in found_links:
                    if href in seen_urls:
                        continue
                    seen_urls.add(href)
                    m = re.search(r"episode-(\d+(?:-\d+)?)", href)
                    ep_num = m.group(1).replace("-", ".") if m else str(len(episodes) + 1)
                    episodes.append(
                        EpisodeItem(
                            id=href,
                            number=ep_num,
                            title=f"Episode {ep_num}",
                            season=1,
                            media_title=item.title,
                        )
                    )

                # DramaCool pages list newest episode first; reverse to chronological order
                episodes.reverse()
            except Exception as e:
                print(f"[DramaCool] Failed to load episodes: {e}")

        return episodes

    async def get_stream(
        self, episode: EpisodeItem, quality: str | None = None
    ) -> StreamInfo:
        """Extract direct HLS .m3u8 stream and subtitles from the episode page."""
        async with httpx.AsyncClient(headers=HEADERS, timeout=12, follow_redirects=True) as client:
            ep_res = await client.get(episode.id)
            soup = BeautifulSoup(ep_res.text, "html.parser")

            embed_url = None
            el = soup.find(attrs={"data-video": True})
            if el:
                embed_url = el.get("data-video")
            if not embed_url:
                ifr = soup.find("iframe")
                embed_url = ifr.get("src") if ifr else None

            if not embed_url:
                raise RuntimeError(f"No video embed found on episode page: {episode.id}")

            # 1. If embed is a 2ivdeo/kisskh source
            if "2ivdeo.buzz" in embed_url or "kisskh" in embed_url:
                stream_info = await self._resolve_2ivdeo(embed_url, episode, client, quality)
                if stream_info:
                    return stream_info

            # 2. Direct m3u8 or mp4
            if embed_url.endswith(".m3u8") or embed_url.endswith(".mp4"):
                return StreamInfo(
                    url=embed_url,
                    title=f"{episode.media_title} - {episode.display_name}",
                    referer=DRAMACOOL_BASE,
                    quality=quality,
                )

            # 3. Generic regex scan of embed target
            res = await client.get(embed_url, timeout=10)
            m3u8_m = re.search(r"https?://[^\s\"\'\<\>]+\.m3u8[^\s\"\'\<\>]*", res.text)
            if m3u8_m:
                return StreamInfo(
                    url=m3u8_m.group(0),
                    title=f"{episode.media_title} - {episode.display_name}",
                    referer=embed_url,
                    quality=quality,
                )

            raise RuntimeError(
                f"Could not extract playable stream from embed: {embed_url}\n"
                f"The host CDN may have temporarily expired this episode link."
            )

    async def _resolve_2ivdeo(
        self,
        embed_url: str,
        episode: EpisodeItem,
        client: httpx.AsyncClient,
        quality: str | None,
    ) -> StreamInfo | None:
        """Resolve stream from 2ivdeo.buzz endpoint using browser fetch emulation headers."""
        m = re.search(r"kisskh/(\d+)", embed_url)
        if not m:
            return None

        ep_id = m.group(1)
        source_url = f"https://2ivdeo.buzz/kisskh/{ep_id}/source"
        headers = {
            "User-Agent": HEADERS["User-Agent"],
            "Referer": embed_url,
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
        }

        try:
            r = await client.get(source_url, headers=headers)
            if r.status_code == 200:
                data = r.json()
                if data.get("status") == "ok" and data.get("source"):
                    subtitles = []
                    for t in data.get("tracks", []):
                        if isinstance(t, dict) and t.get("file"):
                            subtitles.append(t["file"])

                    return StreamInfo(
                        url=data["source"],
                        title=f"{episode.media_title} - {episode.display_name}",
                        referer=embed_url,
                        subtitles=subtitles,
                        quality=quality,
                    )
        except Exception:
            pass

        return None
