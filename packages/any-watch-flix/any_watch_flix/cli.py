#!/usr/bin/env python3
"""any-watch-flix — movies and Western TV from FlixHQ, LK21, IDLIX, SubDL."""
from __future__ import annotations

from any_watch_core.app import run_category_app


def main(argv: list[str] | None = None) -> None:
    run_category_app(
        "flix",
        argv,
        prog="any-watch-flix",
        description=(
            "Stream movies and Western TV shows 🍿 — FlixHQ, LK21, IDLIX, "
            "plus SubDL subtitle downloads."
        ),
    )


if __name__ == "__main__":
    main()
