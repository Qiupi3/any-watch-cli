"""any_watch_core — lightweight streaming & playback engine."""

from .base import Action, BaseProvider, EpisodeItem, MediaItem, MediaType, StreamInfo
from .config import Config, get_config, save_config
from .downloader import download_stream
from .flow import interactive_flow
from .player import is_android, play_stream
from .pooler import pool_search
from .ui import parse_episode_range, prompt_selection

__version__ = "1.0.0"

__all__ = [
    "Action",
    "BaseProvider",
    "EpisodeItem",
    "MediaItem",
    "MediaType",
    "StreamInfo",
    "Config",
    "get_config",
    "save_config",
    "download_stream",
    "interactive_flow",
    "is_android",
    "play_stream",
    "pool_search",
    "parse_episode_range",
    "prompt_selection",
]
