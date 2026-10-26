from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MediaType(str, Enum):
    MOVIE = "movie"
    SERIES = "series"
    ANIME = "anime"
    DRAMA = "drama"


@dataclass
class SubtitleTrack:
    url: str
    label: str = "English"  # "Indonesian", "English", etc.
    lang: str = "eng"       # "ind", "eng", etc.

    def __str__(self) -> str:
        return f"{self.label} ({self.lang}): {self.url}"


@dataclass
class SubtitleResult:
    """A downloadable subtitle file returned by a subtitle-only provider."""

    title: str
    language: str
    url: str
    release: str = ""
    provider: str = "SubDL"

    @property
    def display_tag(self) -> str:
        rel = f" · {self.release}" if self.release else ""
        return f"[{self.provider} | {self.language.upper()}] {self.title}{rel}"


@dataclass
class MediaItem:
    id: str  # unique ID, path, or URL
    title: str  # Display title
    provider: str  # e.g. "FlixHQ", "HiAnime", "DramaCool"
    media_type: MediaType  # movie, series, anime, drama
    year: str | None = None
    category: str = "General"  # e.g. "Movie/Series", "Anime", "Drama"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def display_tag(self) -> str:
        """Formatted tag for pooler selection, e.g. [FlixHQ | TV] Queen of Tears (2024)"""
        tag = f"[{self.provider} | {self.media_type.value.upper()}]"
        yr = f" ({self.year})" if self.year else ""
        return f"{tag} {self.title}{yr}"


@dataclass
class EpisodeItem:
    id: str  # episode data id, path, or url
    number: str  # e.g. "1", "12", "16.1"
    title: str  # title or "Episode 1"
    season: int = 1
    media_title: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        if self.title and self.title.lower() != f"episode {self.number}".lower():
            return f"EP {self.number} - {self.title}"
        return f"Episode {self.number}"


@dataclass
class StreamInfo:
    url: str  # direct m3u8 or mp4
    title: str  # media title for player display
    referer: str = ""
    subtitles: list[SubtitleTrack] = field(default_factory=list)  # softsub tracks
    quality: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class BaseProvider(ABC):
    name: str = "base"
    category: str = "General"
    kind: str = "stream"  # "stream" or "subtitle"
    base_urls: tuple[str, ...] = ()

    @abstractmethod
    async def search(self, query: str) -> list[MediaItem]:
        """Search media asynchronously"""
        pass

    @abstractmethod
    async def get_episodes(
        self, item: MediaItem, season: int | None = None
    ) -> list[EpisodeItem]:
        """Get list of episodes for the media item"""
        pass

    @abstractmethod
    async def get_stream(
        self, episode: EpisodeItem, quality: str | None = None
    ) -> StreamInfo:
        """Extract stream URL and subtitles for an episode"""
        pass


class BaseSubtitleProvider(ABC):
    """Provider that only searches/downloads subtitle files (e.g. SubDL)."""

    name: str = "Subtitles"
    category: str = "General"
    kind: str = "subtitle"
    base_urls: tuple[str, ...] = ()

    @abstractmethod
    async def search_subtitles(
        self, query: str, lang: str = "id"
    ) -> list[SubtitleResult]:
        """Search subtitle files for a movie or show."""
        pass
