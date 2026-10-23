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
from .proxy import StreamProxy
from .pooler import pool_search
from .ui import (
    episode_sort_key,
    parse_episode_range,
    prompt_episode_selection,
    prompt_selection,
    resolve_selected_episodes,
)

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
    "StreamProxy",
    "pool_search",
    "episode_sort_key",
    "parse_episode_range",
    "prompt_episode_selection",
    "prompt_selection",
    "resolve_selected_episodes",
]
