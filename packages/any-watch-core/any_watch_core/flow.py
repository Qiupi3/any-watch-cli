from __future__ import annotations

"""
Common interactive flow: search → pick → episode → stream → play/download.
Used by module CLIs and the master pooler CLI.
"""

import asyncio
import sys
from typing import Optional

from any_watch_core.base import Action, BaseProvider, EpisodeItem, MediaItem
from any_watch_core.downloader import download_stream
from any_watch_core.player import play_stream
from any_watch_core.ui import parse_episode_range, prompt_selection


def _run(coro):  # asyncio.run wrapper
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


def interactive_flow(
    provider: BaseProvider,
    query: str,
    action: Action = Action.PLAY,
    episode_spec: Optional[str] = None,
    season: Optional[int] = None,
    quality: Optional[str] = None,
    player: Optional[str] = None,
    sub_lang: Optional[str] = None,
    single_episode_mode: bool = False,
) -> None:
    """Full interactive session: search → title pick → episode pick → play/download."""

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

    # ----- 4. Resolve which episodes to play -----
    episodes_to_play: list[EpisodeItem] = []

    if len(episodes) == 1:
        # Single-item (movie)
        episodes_to_play = episodes
    elif episode_spec:
        ep_nums = parse_episode_range(episode_spec)
        episodes_to_play = [ep for ep in episodes if int(float(ep.number)) in ep_nums]
        if not episodes_to_play:
            print(f"[!] Episode(s) {episode_spec} not found in available episodes.")
            sys.exit(1)
    else:
        # Interactive episode pick
        ep_titles = [ep.display_name for ep in episodes]
        print(f"\n[~] {len(episodes)} episodes available.")

        if single_episode_mode:
            chosen_ep = prompt_selection(ep_titles, "Select episode")
            if not chosen_ep:
                print("[!] No episode selected.")
                sys.exit(0)
            episodes_to_play = [episodes[ep_titles.index(chosen_ep)]]
        else:
            try:
                user_val = input(
                    f"Episode to watch (e.g. '1', '1-3', '1,5') [{len(episodes)} available] [1]: "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                sys.exit(0)
            ep_spec_input = user_val if user_val else "1"
            ep_nums = parse_episode_range(ep_spec_input)
            episodes_to_play = [ep for ep in episodes if int(float(ep.number)) in ep_nums]
            if not episodes_to_play:
                print("[!] No matching episodes found.")
                sys.exit(1)

    # ----- 5. Stream / download each episode -----
    for ep in episodes_to_play:
        print(f"\n[~] Resolving stream: {ep.display_name} ...")
        try:
            stream = _run(provider.get_stream(ep, quality=quality))
        except Exception as e:
            print(f"[!] Stream extraction failed for {ep.display_name}: {e}")
            continue

        # Filter or re-order subtitles by language preference if requested
        if sub_lang and stream.subtitles:
            filtered = [s for s in stream.subtitles if sub_lang.lower() in s.lower()]
            if filtered:
                stream.subtitles = filtered + [s for s in stream.subtitles if s not in filtered]

        if action == Action.DOWNLOAD:
            download_stream(stream, category=provider.category)
        else:
            print(f"[+] Playing: {stream.title}")
            if stream.subtitles:
                print(f"[+] Subtitles: {stream.subtitles[0]}")
            play_stream(stream, custom_player=player)
