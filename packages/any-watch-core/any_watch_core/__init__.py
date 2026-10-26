"""any_watch_core — lightweight streaming & playback engine."""

from .base import (
    BaseProvider,
    BaseSubtitleProvider,
    EpisodeItem,
    MediaItem,
    MediaType,
    StreamInfo,
    SubtitleResult,
    SubtitleTrack,
)
from .catalog import (
    CATEGORIES,
    PROVIDER_SPECS,
    CategorySpec,
    ProviderSpec,
    find_spec,
    format_catalog,
    get_category,
    get_specs,
    load_provider,
    load_providers,
)
from .config import Config, get_config, save_config
from .extract import (
    DEFAULT_HEADERS,
    find_embeds,
    find_media_urls,
    find_subtitle_urls,
    resolve_stream,
)
from .flow import interactive_flow
from .player import is_android, play_stream
from .proxy import StreamProxy
from .pooler import pool_search
from .subtitles import download_subtitle
from .ui import (
    episode_sort_key,
    parse_episode_range,
    prompt_episode_selection,
    prompt_selection,
    resolve_selected_episodes,
)

__version__ = "1.1.0"

__all__ = [
    "BaseProvider",
    "BaseSubtitleProvider",
    "EpisodeItem",
    "MediaItem",
    "MediaType",
    "StreamInfo",
    "SubtitleResult",
    "SubtitleTrack",
    "CATEGORIES",
    "PROVIDER_SPECS",
    "CategorySpec",
    "ProviderSpec",
    "find_spec",
    "format_catalog",
    "get_category",
    "get_specs",
    "load_provider",
    "load_providers",
    "Config",
    "get_config",
    "save_config",
    "DEFAULT_HEADERS",
    "find_embeds",
    "find_media_urls",
    "find_subtitle_urls",
    "resolve_stream",
    "interactive_flow",
    "is_android",
    "play_stream",
    "StreamProxy",
    "pool_search",
    "episode_sort_key",
    "download_subtitle",
    "parse_episode_range",
    "prompt_episode_selection",
    "prompt_selection",
    "resolve_selected_episodes",
]
