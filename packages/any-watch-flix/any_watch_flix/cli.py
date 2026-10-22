#!/usr/bin/env python3
"""any-watch-flix — Stream Movies & TV Shows from FlixHQ."""
from __future__ import annotations

import argparse
import sys

from any_watch_core.flow import interactive_flow
from any_watch_flix.provider import FlixHQProvider


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="any-watch-flix",
        description="Stream Movies & Western TV Shows via FlixHQ 🍿",
    )
    parser.add_argument("query", nargs="?", help="Movie or show name to search")
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

    args = parser.parse_args(argv)

    if not args.query:
        try:
            args.query = input("Enter movie/show name: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if not args.query:
            parser.print_help()
            sys.exit(1)

    provider = FlixHQProvider()
    interactive_flow(
        provider=provider,
        query=args.query,
        episode_spec=args.episode,
        season=args.season,
        quality=args.quality,
        player=args.player,
        sub_lang=args.sub,
    )


if __name__ == "__main__":
    main()
