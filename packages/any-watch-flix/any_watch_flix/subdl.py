from __future__ import annotations

import os

import httpx

from any_watch_core.base import BaseSubtitleProvider, SubtitleResult
from any_watch_core.config import get_config
from any_watch_core.extract import DEFAULT_HEADERS


SUBDL_API_URL = "https://api.subdl.com/api/v1/subtitles"
SUBDL_DOWNLOAD_BASE = "https://dl.subdl.com"


class SubDLProvider(BaseSubtitleProvider):
    """Official SubDL REST API client (Indonesian & English subtitles)."""

    name = "SubDL"
    category = "Flix"
    base_urls = ("https://subdl.com", "https://api.subdl.com")

    def __init__(self, api_key: str | None = None) -> None:
        config = get_config()
        self.api_key = (
            api_key
            or os.environ.get("SUBDL_API_KEY", "")
            or getattr(config, "subdl_api_key", "")
        )

    async def search_subtitles(
        self, query: str, lang: str = "id"
    ) -> list[SubtitleResult]:
        if not self.api_key:
            raise RuntimeError(
                "SubDL needs a free API key. Create one at "
                "https://subdl.com/panel/api then either export "
                "SUBDL_API_KEY=your_key or put \"subdl_api_key\": \"your_key\" "
                "in ~/.config/any-watch/config.json."
            )

        language = "EN" if lang.lower().startswith("en") else "ID"
        params = {
            "api_key": self.api_key,
            "film_name": query,
            "languages": language,
            "subs_per_page": 30,
        }

        async with httpx.AsyncClient(
            headers=DEFAULT_HEADERS, timeout=20, follow_redirects=True
        ) as client:
            response = await client.get(SUBDL_API_URL, params=params)
            try:
                data = response.json()
            except ValueError:
                data = None

            if response.status_code >= 400:
                if isinstance(data, dict):
                    detail = (
                        data.get("message")
                        or data.get("error")
                        or f"HTTP {response.status_code}"
                    )
                    raise RuntimeError(f"SubDL API rejected the request: {detail}")
                response.raise_for_status()

        if not isinstance(data, dict):
            raise RuntimeError("SubDL returned an unexpected response.")
        if data.get("status") is False:
            raise RuntimeError(
                "SubDL API rejected the request: "
                f"{data.get('error') or data.get('message') or 'unknown error'}"
            )

        results: list[SubtitleResult] = []
        for item in data.get("subtitles", []) or []:
            if not isinstance(item, dict):
                continue
            url = item.get("url") or ""
            if not url:
                continue
            if not url.startswith("http"):
                url = f"{SUBDL_DOWNLOAD_BASE}{url}"

            code = str(item.get("language", language)).upper()
            language_label = "Indonesian" if code in ("ID", "IND") else (
                "English" if code in ("EN", "ENG") else code
            )
            name = (
                item.get("name")
                or item.get("release")
                or item.get("filename")
                or query
            )
            results.append(
                SubtitleResult(
                    title=name,
                    language=language_label,
                    url=url,
                    release=str(item.get("release") or ""),
                    provider=self.name,
                )
            )

        return results
