#!/usr/bin/env python3
"""any-watch-drama — Stream KDrama & CDrama from DramaCool."""
from __future__ import annotations

import argparse
import sys

from any_watch_core.base import Action
from any_watch_core.flow import interactive_flow
from any_watch_drama.provider import DramaProvider


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="any-watch-drama",
        description="Stream Korean & Chinese Dramas via DramaCool 📺",
    )
    parser.add_argument("query", nargs="?", help="Drama name to search")
    parser.add_argument(
        "-a", "--action",
        choices=["play", "download"],
        default="play",
        help="Action: play (default) or download",
    )
    parser.add_argument("-e", "--episode", help="Episode(s) e.g. '1', '3-6', '1,4'")
    parser.add_argument("-s", "--season", type=int, help="Season number")
    parser.add_argument("-q", "--quality", help="Quality hint")
    parser.add_argument("-p", "--player", help="Player to use (mpv, iina, vlc)")
    parser.add_argument("--sub", help="Preferred subtitle language")

    args = parser.parse_args(argv)

    if not args.query:
        try:
            args.query = input("Enter drama name: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if not args.query:
            parser.print_help()
            sys.exit(1)

    provider = DramaProvider()
    interactive_flow(
        provider=provider,
        query=args.query,
        action=Action(args.action),
        episode_spec=args.episode,
        season=args.season,
        quality=args.quality,
        player=args.player,
        sub_lang=args.sub,
    )


if __name__ == "__main__":
    main()
