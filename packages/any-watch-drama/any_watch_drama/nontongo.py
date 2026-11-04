from __future__ import annotations

from .gmr import GmrThemeProvider


class NontongoProvider(GmrThemeProvider):
    name = "Nontongo"
    base_urls = ("https://nontongo.site",)
    episode_path_markers = ("/episode/", "/eps/", "/nonton-", "?eps=", "/film-drama/")
    max_quality = "1080p"
    subtitle_format = "Hardsub"
    feasibility = "Sedang"
    note = "Encrypted window.__PX player decrypted to HLS."
