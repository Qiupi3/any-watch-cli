from __future__ import annotations

"""KissKH provider.

Metadata comes from the public KissKH REST API. Episode playback is resolved
through ``/api/DramaList/Episode/{id}.png`` which returns an HLS source plus
soft-subtitle tracks. The ``2ivdeo`` player endpoint is kept as a fallback for
older episodes whose API payload is empty.
"""

import re
from typing import Any, Optional
from urllib.parse import urljoin

import httpx

from any_watch_core.base import (
    BaseProvider,
    EpisodeItem,
    MediaItem,
    MediaType,
    StreamInfo,
    SubtitleTrack,
)
from any_watch_core.extract import (
    DEFAULT_HEADERS,
    guess_lang,
    js_unescape,
    resolve_stream,
    sort_key,
)

KISSKH_WEB_BASES = ("https://kisskh.co", "https://kisskh.me", "https://kisskh.tv")
KISSKH_API_BASES = (
    "https://api.kisskh.co",
    "https://api.kisskh.me",
    "https://api.kisskh.tv",
)
KISSKH_FALLBACK_PLAYER = "https://2ivdeo.buzz/kisskh/{episode_id}/source"

_API_HEADERS = {
    **DEFAULT_HEADERS,
    "Accept": "application/json, text/plain, */*",
    "Origin": "https://kisskh.co",
    "Referer": "https://kisskh.co/",
}


def _ci_get(data: dict[str, Any], *keys: str) -> Any:
    """Case-insensitive dictionary lookup used for the loosely-typed API."""
    lowered = {str(key).lower(): value for key, value in data.items()}
    for key in keys:
        if key.lower() in lowered:
            return lowered[key.lower()]
    return None


def _as_list(data: Any, *keys: str) -> list[Any]:
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in keys:
            value = _ci_get(data, key)
            if isinstance(value, list):
                return value
    return []


def _text(value: Any) -> str:
    return js_unescape(str(value or "")).strip()


class KissKHProvider(BaseProvider):
    name = "KissKH"
    category = "Drama"
    base_urls = KISSKH_WEB_BASES
    api_bases = KISSKH_API_BASES

    # ------------------------------------------------------------------ API
    async def _api_json(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: Optional[dict[str, Any]] = None,
    ) -> Optional[Any]:
        for base in (*self.api_bases, *self.base_urls):
            try:
                response = await client.get(
                    f"{base}{path}",
                    params=params,
                    headers=_API_HEADERS,
                    timeout=15,
                    follow_redirects=True,
                )
            except Exception:
                continue
            if response.status_code >= 400 or not response.text.strip():
                continue
            try:
                return response.json()
            except ValueError:
                continue
        return None

    # --------------------------------------------------------------- search
    async def search(self, query: str) -> list[MediaItem]:
        results: list[MediaItem] = []
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=20, follow_redirects=True
        ) as client:
            payload = await self._api_json(
                client, "/api/DramaList/Search", {"q": query, "type": 0}
            )
            entries = _as_list(payload, "data", "results", "dramas", "items")
            seen: set[str] = set()

            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                drama_id = _text(
                    _ci_get(entry, "id", "dramaId", "drama_id")
                )
                if not drama_id:
                    continue
                title = _text(
                    _ci_get(entry, "title", "label", "name", "dramaName")
                )
                if len(title) < 2 or drama_id in seen:
                    continue
                seen.add(drama_id)

                year = _text(_ci_get(entry, "year", "releaseYear"))
                if not year:
                    match = re.search(r"(?:19|20)\d{2}", title)
                    year = match.group(0) if match else ""

                country = _text(_ci_get(entry, "country", "countryName"))
                results.append(
                    MediaItem(
                        id=drama_id,
                        title=title,
                        provider=self.name,
                        media_type=MediaType.DRAMA,
                        year=year or None,
                        category=self.category,
                        extra={
                            "drama_id": drama_id,
                            "country": country,
                            "episodes": _ci_get(entry, "episodesCount", "episodes"),
                            "status": _text(_ci_get(entry, "status")),
                        },
                    )
                )

        return results

    # ------------------------------------------------------------- episodes
    async def get_episodes(
        self, item: MediaItem, season: int | None = None
    ) -> list[EpisodeItem]:
        drama_id = str(item.extra.get("drama_id") or item.id)
        episodes: list[EpisodeItem] = []

        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=20, follow_redirects=True
        ) as client:
            payload = await self._api_json(
                client,
                f"/api/DramaList/Drama/{drama_id}",
                {"isq": "false"},
            )
            entries = _as_list(payload, "episodes", "Episodes", "data")
            seen: set[str] = set()

            for index, entry in enumerate(entries, start=1):
                if not isinstance(entry, dict):
                    continue
                episode_id = _text(
                    _ci_get(entry, "id", "episodeId", "episode_id")
                )
                if not episode_id or episode_id in seen:
                    continue

                number = _text(
                    _ci_get(entry, "number", "episodeNumber", "episode", "ep")
                )
                if not number:
                    number = str(index)
                number = re.sub(r"^(\d+)\.0+$", r"\1", number)

                season_value = _ci_get(entry, "season", "seasonNumber")
                try:
                    season_num = int(season_value)
                except (TypeError, ValueError):
                    season_num = season or 1
                if season is not None and season_num != season:
                    continue

                seen.add(episode_id)
                episodes.append(
                    EpisodeItem(
                        id=episode_id,
                        number=number,
                        title=f"Episode {number}",
                        season=season_num,
                        media_title=item.title,
                        extra={
                            "drama_id": drama_id,
                            "sub": _ci_get(entry, "sub", "subtitles"),
                        },
                    )
                )

            episodes.sort(key=lambda ep: (ep.season, sort_key(ep.number)))

        return episodes

    # --------------------------------------------------------------- stream
    async def get_stream(
        self, episode: EpisodeItem, quality: str | None = None
    ) -> StreamInfo:
        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=20, follow_redirects=True
        ) as client:
            payload = await self._api_json(
                client,
                f"/api/DramaList/Episode/{episode.id}.png",
                {"err": "false", "ts": "", "time": "", "kkey": ""},
            )

            video = ""
            subtitles: list[SubtitleTrack] = []
            if isinstance(payload, dict):
                video = _text(_ci_get(payload, "video", "source", "stream", "url"))
                subtitles = self._parse_subtitles(
                    _as_list(payload, "subtitles", "tracks", "captions")
                )

            if not video:
                video, fallback_subs = await self._resolve_fallback_player(
                    client, episode
                )
                if not subtitles:
                    subtitles = fallback_subs

            if not video:
                raise RuntimeError(
                    "KissKH did not return a playable source for this episode. "
                    "The API mirror may be blocked or the episode is region-locked."
                )

            if video.startswith("//"):
                video = f"https:{video}"
            elif video.startswith("/"):
                video = urljoin("https://kisskh.co", video)

            final_referer = "https://kisskh.co/"
            if not re.search(r"\.(?:m3u8|mp4|webm)(?:[?#]|$)", video, re.I):
                resolved, referer, extra_subs = await resolve_stream(
                    client, video, referer="https://kisskh.co/"
                )
                if not resolved:
                    raise RuntimeError(
                        "KissKH returned a player page but no playable media URL. "
                        "Try another episode, mirror, or drama site."
                    )
                video = resolved
                final_referer = referer or final_referer
                if not subtitles:
                    subtitles = extra_subs

            return StreamInfo(
                url=video,
                title=f"{episode.media_title} - {episode.display_name}",
                referer=final_referer,
                subtitles=subtitles,
                quality=quality,
            )

    async def _resolve_fallback_player(
        self, client: httpx.AsyncClient, episode: EpisodeItem
    ) -> tuple[str, list[SubtitleTrack]]:
        url = KISSKH_FALLBACK_PLAYER.format(episode_id=episode.id)
        headers = {
            **_API_HEADERS,
            "Referer": "https://kisskh.co/",
        }
        try:
            response = await client.get(url, headers=headers, timeout=15)
            if response.status_code >= 400:
                return "", []
            data = response.json()
        except Exception:
            return "", []

        if not isinstance(data, dict):
            return "", []
        if str(_ci_get(data, "status") or "ok").lower() not in ("ok", "success"):
            return "", []

        video = _text(_ci_get(data, "source", "video", "url"))
        subtitles = self._parse_subtitles(
            _as_list(data, "tracks", "subtitles", "captions")
        )
        return video, subtitles

    @staticmethod
    def _parse_subtitles(entries: list[Any]) -> list[SubtitleTrack]:
        tracks: list[SubtitleTrack] = []
        seen: set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            url = _text(_ci_get(entry, "src", "file", "url", "source"))
            if not url:
                continue
            if url.startswith("//"):
                url = f"https:{url}"
            elif url.startswith("/"):
                url = urljoin("https://kisskh.co", url)
            if url in seen:
                continue
            seen.add(url)

            label = _text(_ci_get(entry, "label", "language", "lan", "land"))
            lang_code = _text(_ci_get(entry, "land", "lang", "languageCode"))
            if not label:
                label = lang_code or "Subtitle"
            guessed_label, guessed_code = guess_lang(f"{label} {lang_code} {url}")
            if guessed_code != "other":
                label, lang_code = guessed_label, guessed_code
            tracks.append(
                SubtitleTrack(
                    url=url,
                    label=label or "Subtitle",
                    lang=lang_code or guessed_code,
                )
            )
        return tracks
