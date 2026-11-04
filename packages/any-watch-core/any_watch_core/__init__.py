"""any_watch_core — lightweight streaming & playback engine."""

from .version import __version__

from .base import (
    BaseProvider,
    EpisodeItem,
    MediaItem,
    MediaType,
    StreamInfo,
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
    resolve_playable_url,
    resolve_stream,
)
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
from .updates import check_for_update, maybe_check, perform_update

__all__ = [
    "BaseProvider",
    "EpisodeItem",
    "MediaItem",
    "MediaType",
    "StreamInfo",
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
    "resolve_playable_url",
    "resolve_stream",
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
    "check_for_update",
    "maybe_check",
    "perform_update",
    "__version__",
]
