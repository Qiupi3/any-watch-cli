#!/usr/bin/env python3
"""any-watch-anime — Stream Anime from HiAnime."""
from __future__ import annotations

import argparse
import sys

from any_watch_anime.provider import HiAnimeProvider
from any_watch_core.base import Action
from any_watch_core.flow import interactive_flow


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="any-watch-anime",
        description="Stream Anime via HiAnime 🎌",
    )
    parser.add_argument("query", nargs="?", help="Anime name to search")
    parser.add_argument(
        "-a", "--action",
        choices=["play", "download"],
        default="play",
        help="Action: play (default) or download",
    )
    parser.add_argument("-e", "--episode", help="Episode(s) e.g. '1', '3-6', '1,4'")
    parser.add_argument("-q", "--quality", help="Quality hint")
    parser.add_argument("-p", "--player", help="Player to use (mpv, iina, vlc)")
    parser.add_argument("--sub", help="Preferred subtitle language")

    args = parser.parse_args(argv)

    if not args.query:
        try:
            args.query = input("Enter anime name: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if not args.query:
            parser.print_help()
            sys.exit(1)

    provider = HiAnimeProvider()
    interactive_flow(
        provider=provider,
        query=args.query,
        action=Action(args.action),
        episode_spec=args.episode,
        quality=args.quality,
        player=args.player,
        sub_lang=args.sub,
    )


if __name__ == "__main__":
    main()
