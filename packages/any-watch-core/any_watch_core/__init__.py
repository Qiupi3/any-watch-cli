"""any_watch_core — lightweight streaming & playback engine."""

from .base import (
    BaseProvider,
    EpisodeItem,
    MediaItem,
    MediaType,
    StreamInfo,
    SubtitleTrack,
)
from .config import Config, get_config, save_config
from .flow import interactive_flow
from .player import is_android, play_stream
from .pooler import pool_search
from .ui import parse_episode_range, prompt_selection

__version__ = "1.0.0"

__all__ = [
    "BaseProvider",
    "EpisodeItem",
    "MediaItem",
    "MediaType",
    "StreamInfo",
    "SubtitleTrack",
    "Config",
    "get_config",
    "save_config",
    "interactive_flow",
    "is_android",
    "play_stream",
    "pool_search",
    "parse_episode_range",
    "prompt_selection",
]
