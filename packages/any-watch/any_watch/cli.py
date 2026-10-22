#!/usr/bin/env python3
"""any-watch — Universal CLI pooler for Movies, TV, Anime & Drama."""
from __future__ import annotations

import argparse
import sys
from typing import Optional

from any_watch_core.base import Action, MediaItem
from any_watch_core.flow import _run, interactive_flow
from any_watch_core.pooler import pool_search
from any_watch_core.ui import prompt_selection


def get_providers(limit: Optional[str] = None):
    providers = []
    # Try importing each module gracefully
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
    parser = argparse.ArgumentParser(
        prog="any-watch",
        description="Universal terminal streaming suite — search Movies, TV, Anime & Drama 🎬",
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Module subcommands")

    # Master pooler arguments (default)
    parser.add_argument("query", nargs="?", help="What to watch (searches across all providers)")
    parser.add_argument("-a", "--action", choices=["play", "download"], default="play", help="Action: play (default) or download")
    parser.add_argument("-e", "--episode", help="Episode(s) e.g. '1', '2-4'")
    parser.add_argument("-s", "--season", type=int, help="Season number")
    parser.add_argument("-q", "--quality", help="Quality e.g. '1080p', '720p'")
    parser.add_argument("-p", "--player", help="Player to use (mpv, iina, vlc)")
    parser.add_argument("--sub", help="Preferred subtitle language (e.g. indonesian, english)")
    parser.add_argument("--provider", choices=["flix", "anime", "drama"], help="Limit search to one provider")

    # Subcommands for flix, anime, drama
    flix_parser = subparsers.add_parser("flix", help="🍿 Movies & TV Shows (FlixHQ)")
    flix_parser.add_argument("query", nargs="?", help="Movie or show name")
    flix_parser.add_argument("-a", "--action", choices=["play", "download"], default="play")
    flix_parser.add_argument("-e", "--episode")
    flix_parser.add_argument("-s", "--season", type=int)
    flix_parser.add_argument("-q", "--quality")
    flix_parser.add_argument("-p", "--player")
    flix_parser.add_argument("--sub")

    anime_parser = subparsers.add_parser("anime", help="🎌 Anime (HiAnime)")
    anime_parser.add_argument("query", nargs="?", help="Anime name")
    anime_parser.add_argument("-a", "--action", choices=["play", "download"], default="play")
    anime_parser.add_argument("-e", "--episode")
    anime_parser.add_argument("-q", "--quality")
    anime_parser.add_argument("-p", "--player")
    anime_parser.add_argument("--sub")

    drama_parser = subparsers.add_parser("drama", help="📺 KDrama & CDrama (DramaCool)")
    drama_parser.add_argument("query", nargs="?", help="Drama name")
    drama_parser.add_argument("-a", "--action", choices=["play", "download"], default="play")
    drama_parser.add_argument("-e", "--episode")
    drama_parser.add_argument("-s", "--season", type=int)
    drama_parser.add_argument("-q", "--quality")
    drama_parser.add_argument("-p", "--player")
    drama_parser.add_argument("--sub")

    args = parser.parse_args(argv)

    # Route subcommands if used
    if args.subcommand == "flix":
        from any_watch_flix.cli import main as flix_main
        sub_args = sys.argv[2:] if argv is None else argv[1:]
        flix_main(sub_args)
        return
    elif args.subcommand == "anime":
        from any_watch_anime.cli import main as anime_main
        sub_args = sys.argv[2:] if argv is None else argv[1:]
        anime_main(sub_args)
        return
    elif args.subcommand == "drama":
        from any_watch_drama.cli import main as drama_main
        sub_args = sys.argv[2:] if argv is None else argv[1:]
        drama_main(sub_args)
        return

    # Master pooler flow
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

    # Display unified selector
    display_tags = [item.display_tag for item in all_results]
    chosen_tag = prompt_selection(display_tags, "Select what to watch")
    if not chosen_tag:
        print("[!] Nothing selected, exiting.")
        sys.exit(0)

    selected: MediaItem = all_results[display_tags.index(chosen_tag)]
    print(f"\n[+] Selected: {selected.title}  [{selected.provider}]")

    # Match selected item back to its provider
    target_provider = next(
        (p for p in providers if p.name.lower() in selected.provider.lower() or selected.provider.lower() in p.name.lower()),
        providers[0],
    )

    interactive_flow(
        provider=target_provider,
        query=selected.title,
        action=Action(args.action),
        episode_spec=args.episode,
        season=args.season,
        quality=args.quality,
        player=args.player,
        sub_lang=args.sub,
        single_episode_mode=True,
    )


if __name__ == "__main__":
    main()
