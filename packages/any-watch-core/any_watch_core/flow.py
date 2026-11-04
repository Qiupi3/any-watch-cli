from __future__ import annotations

"""
Interactive streaming flow: search → title pick → episode pick → stream.
Stream-only architecture with dual English & Indonesian softsub support.
"""

import asyncio
import sys
from typing import Optional

from any_watch_core.base import BaseProvider, EpisodeItem, MediaItem, StreamInfo
from any_watch_core.config import get_config
from any_watch_core.player import play_stream
from any_watch_core.ui import (
    episode_sort_key,
    prompt_episode_selection,
    prompt_selection,
    resolve_selected_episodes,
)


def _play_candidates(stream: StreamInfo) -> list[StreamInfo]:
    """The stream plus any alternate mirrors the provider resolved.

    Alternates are tried in order when the player rejects a link (typical for
    IP-bound googlevideo/MP4 mirrors), each with a freshly minted URL.
    """
    alternates = [
        StreamInfo(
            url=alt["url"],
            title=stream.title,
            referer=alt.get("referer", ""),
            subtitles=list(alt.get("subtitles") or []),
            quality=stream.quality,
            extra={"alternate": True},
        )
        for alt in (stream.extra or {}).get("alternates") or []
        if alt.get("url") and alt.get("url") != stream.url
    ]
    return [stream, *alternates]


def _run(coro):  # Safe asyncio.run wrapper that never re-awaits on error
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # No loop running: run directly.
        return asyncio.run(coro)

    # A loop is already running in this thread, run in a separate thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def interactive_flow(
    provider: BaseProvider,
    query: Optional[str] = None,
    item: Optional[MediaItem] = None,
    episode_spec: Optional[str] = None,
    season: Optional[int] = None,
    quality: Optional[str] = None,
    player: Optional[str] = None,
    sub_lang: Optional[str] = None,
    single_episode_mode: bool = True,
) -> None:
    """Stream-only interactive session: search/item → episode pick → stream."""
    cfg = get_config()
    chosen_sub = (sub_lang or cfg.sub_language or "eng").lower()

    selected_item = item

    # If item is not provided, perform search and prompt user to pick
    if not selected_item:
        if not query:
            print("[!] No search query or item provided.")
            sys.exit(1)

        # ----- 1. Search -----
        print(f"\n[~] Searching '{query}' via {provider.name}...")
        items: list[MediaItem] = _run(provider.search(query))

        if not items:
            print(f"[!] No results found for '{query}'")
            sys.exit(1)

        # ----- 2. Pick title -----
        titles = [it.display_tag for it in items]
        chosen_title = prompt_selection(titles, f"Select a title from {provider.name}")
        if not chosen_title:
            print("[!] No title selected, exiting.")
            sys.exit(0)

        selected_item = items[titles.index(chosen_title)]
        print(f"\n[+] Selected: {selected_item.title}")

    # ----- 3. Get episodes -----
    print("[~] Fetching episode list...")
    episodes: list[EpisodeItem] = _run(provider.get_episodes(selected_item, season=season))

    if not episodes:
        print("[!] No episodes found.")
        sys.exit(1)

    # Naturally sort episodes to ensure strictly correct numerical order
    episodes.sort(key=episode_sort_key)

    # ----- 4. Resolve which episodes to play -----
    episodes_to_play: list[EpisodeItem] = []

    if len(episodes) == 1:
        episodes_to_play = episodes
    elif episode_spec:
        episodes_to_play = resolve_selected_episodes(episodes, episode_spec)
        if not episodes_to_play:
            print(f"[!] Episode(s) {episode_spec} not found in available episodes.")
            sys.exit(1)
    else:
        episodes_to_play = prompt_episode_selection(episodes)
        if not episodes_to_play:
            print("[!] No episode selected, exiting.")
            sys.exit(0)

    # ----- 5. Stream each episode -----
    for ep in episodes_to_play:
        print(f"\n[~] Resolving stream for {ep.display_name} ...")
        try:
            stream = _run(provider.get_stream(ep, quality=quality))
        except Exception as e:
            print(f"[!] Stream extraction failed for {ep.display_name}: {e}")
            continue

        fallback = (stream.extra or {}).get("fallback")
        if fallback:
            print(
                f"[i] {provider.name} has no working player links right now "
                f"(dead file hosts); using {fallback} for this episode."
            )

        if stream.subtitles:
            sub_labels = [f"{getattr(s, 'label', str(s))} ({getattr(s, 'lang', 'other')})" for s in stream.subtitles]
            print(f"[+] Loaded softsub tracks: {', '.join(sub_labels)}")
            active_label = "Indonesian" if chosen_sub in ("ind", "id", "indonesian") else "English"
            print(f"[+] Active default subtitle: {active_label} (press 'j' in MPV to switch)")

        candidates = _play_candidates(stream)
        for index, candidate in enumerate(candidates):
            if index:
                print(
                    f"[~] Previous mirror was rejected by the player; "
                    f"trying mirror {index + 1}/{len(candidates)} ..."
                )
            print(f"[+] Launching player: {candidate.title}")
            if play_stream(
                candidate,
                custom_player=player,
                sub_lang=chosen_sub,
                report_failure=index == len(candidates) - 1,
            ):
                break
        else:
            print(
                "[!] No mirror could be played. The hosts may be down, "
                "geo-blocked, or IP-bound; try another site or episode."
            )
