#!/usr/bin/env python3
"""any-watch — universal terminal streaming suite (Flix / Anime / Drama)."""
from __future__ import annotations

import sys
from importlib import import_module

from any_watch_core.app import run_master_app

SUBCOMMANDS = {
    "flix": "any_watch_flix.cli",
    "anime": "any_watch_anime.cli",
    "drama": "any_watch_drama.cli",
}


def _dispatch(subcommand: str, args: list[str]) -> None:
    module_name = SUBCOMMANDS[subcommand]
    try:
        module = import_module(module_name)
    except ImportError:
        print(
            f"[!] The '{subcommand}' package is not installed. "
            f"Install any-watch-{subcommand} to use `any-watch {subcommand}`."
        )
        sys.exit(1)
    module.main(args)


OPTIONS_WITH_VALUE = {
    "-e",
    "--episode",
    "-s",
    "--season",
    "-q",
    "--quality",
    "-p",
    "--player",
    "--sub",
    "--provider",
    "--site",
}

# Options that only exist on the master CLI. When one is present before the
# first positional, treat the next word as a search query, not a subcommand.
MASTER_ONLY_OPTIONS = {
    "--pick",
    "--site",
    "--list-sites",
    "--provider",
}


def _split_subcommand(args: list[str]) -> tuple[str | None, list[str]]:
    """Find a category subcommand at the first non-option position.

    Flags may precede the subcommand, e.g. ``any-watch -q 1080p flix "Inception"``.
    """
    index = 0
    while index < len(args):
        argument = args[index]
        option = argument.split("=", 1)[0]
        if option in MASTER_ONLY_OPTIONS:
            return None, args
        if argument in OPTIONS_WITH_VALUE:
            index += 2
            continue
        if argument.startswith("-"):
            index += 1
            continue
        if argument.lower() in SUBCOMMANDS:
            return argument.lower(), args[:index] + args[index + 1 :]
        break
    return None, args


def main(argv: list[str] | None = None) -> None:
    raw_args = sys.argv[1:] if argv is None else list(argv)

    subcommand, sub_args = _split_subcommand(raw_args)
    if subcommand:
        _dispatch(subcommand, sub_args)
        return

    run_master_app(raw_args)


if __name__ == "__main__":
    main()
