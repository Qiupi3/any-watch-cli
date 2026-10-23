#!/usr/bin/env python3
"""any-watch — Universal CLI pooler for Movies, TV, Anime & Drama."""
from __future__ import annotations

import argparse
import sys
from typing import Optional

from any_watch_core.base import MediaItem
from any_watch_core.flow import _run, interactive_flow
from any_watch_core.pooler import pool_search
from any_watch_core.ui import prompt_selection

SUBCOMMANDS = {"flix", "anime", "drama"}


def get_providers(limit: Optional[str] = None):
    providers = []
    try:
        from any_watch_flix.provider import FlixHQProvider
        if not limit or limit in ("flix", "flixhq", "movie", "tv"):
            providers.append(FlixHQProvider())
    except ImportError:
        pass

    try:
        from any_watch_anime.provider import HiAnimeProvider
        if not limit or limit in ("anime", "hianime"):
            providers.append(HiAnimeProvider())
    except ImportError:
        pass

    try:
        from any_watch_drama.provider import DramaProvider
        if not limit or limit in ("drama", "dramacool", "kdrama", "cdrama"):
            providers.append(DramaProvider())
    except ImportError:
        pass

    return providers


def main(argv: list[str] | None = None) -> None:
    raw_args = sys.argv[1:] if argv is None else argv

    # 1. Route directly if a known subcommand (flix, anime, drama) is found as a command keyword
    sub_cmd = None
    sub_idx = -1
    opt_with_arg = {"-e", "--episode", "-s", "--season", "-q", "--quality", "-p", "--player", "--sub", "--provider"}
    i = 0
    while i < len(raw_args):
        arg = raw_args[i]
        if arg in opt_with_arg:
            i += 2
            continue
        elif arg.startswith("-"):
            i += 1
            continue
        else:
            if arg.lower() in SUBCOMMANDS:
                sub_cmd = arg.lower()
                sub_idx = i
            break

    if sub_cmd and sub_idx >= 0:
        sub_args = raw_args[:sub_idx] + raw_args[sub_idx + 1:]
        if sub_cmd == "flix":
            from any_watch_flix.cli import main as flix_main
            flix_main(sub_args)
            return
        elif sub_cmd == "anime":
            from any_watch_anime.cli import main as anime_main
            anime_main(sub_args)
            return
        elif sub_cmd == "drama":
            from any_watch_drama.cli import main as drama_main
            drama_main(sub_args)
            return

    # 2. Otherwise, treat as Master Pooler parser (allowing any title like 'hotel del luna')
    parser = argparse.ArgumentParser(
        prog="any-watch",
        description="Universal terminal streaming suite — search Movies, TV, Anime & Drama 🎬",
        epilog=(
            "Subcommands:\n"
            "  any-watch flix <query>     🍿 Movies & Western TV (FlixHQ)\n"
            "  any-watch anime <query>    🎌 Anime (HiAnime)\n"
            "  any-watch drama <query>    📺 KDrama & CDrama (DramaCool)\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", nargs="?", help="What to watch (searches across all providers)")
    parser.add_argument("-e", "--episode", help="Episode(s) e.g. '1', '2-4'")
    parser.add_argument("-s", "--season", type=int, help="Season number")
    parser.add_argument("-q", "--quality", help="Quality e.g. '1080p', '720p'")
    parser.add_argument("-p", "--player", help="Player to use (mpv, iina, vlc)")
    parser.add_argument(
        "--sub",
        choices=["ind", "eng"],
        default=None,
        help="Preferred subtitle language: ind (Indonesian) or eng (English)",
    )
    parser.add_argument("--provider", choices=["flix", "anime", "drama"], help="Limit search to one provider")

    args = parser.parse_args(raw_args)

    if not args.query:
        try:
            args.query = input("What would you like to watch? ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if not args.query:
            parser.print_help()
            sys.exit(1)

    providers = get_providers(args.provider)
    if not providers:
        print("[!] No providers installed. Install any-watch-flix, any-watch-anime, or any-watch-drama.")
        sys.exit(1)

    provider_names = ", ".join(p.name for p in providers)
    print(f"\n[~] Searching '{args.query}' across {provider_names}...")
    all_results: list[MediaItem] = _run(pool_search(providers, args.query))

    if not all_results:
        print(f"[!] No results found for '{args.query}' across {provider_names}.")
        sys.exit(1)

    display_tags = [item.display_tag for item in all_results]
    chosen_tag = prompt_selection(display_tags, "Select what to watch")
    if not chosen_tag:
        print("[!] Nothing selected, exiting.")
        sys.exit(0)

    selected: MediaItem = all_results[display_tags.index(chosen_tag)]
    print(f"\n[+] Selected: {selected.title}  [{selected.provider}]")

    target_provider = next(
        (p for p in providers if p.name.lower() in selected.provider.lower() or selected.provider.lower() in p.name.lower()),
        providers[0],
    )

    interactive_flow(
        provider=target_provider,
        item=selected,
        episode_spec=args.episode,
        season=args.season,
        quality=args.quality,
        player=args.player,
        sub_lang=args.sub,
        single_episode_mode=True,
    )


if __name__ == "__main__":
    main()
