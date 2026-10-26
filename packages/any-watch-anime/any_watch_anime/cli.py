#!/usr/bin/env python3
"""any-watch-anime — anime from HiAnime, AnoBoy, Oploverz, OtakuDesu, Samehadaku."""
from __future__ import annotations

from any_watch_core.app import run_category_app


def main(argv: list[str] | None = None) -> None:
    run_category_app(
        "anime",
        argv,
        prog="any-watch-anime",
        description=(
            "Stream anime sub Indo 🎌 — HiAnime, AnoBoy, Oploverz, OtakuDesu "
            "and Samehadaku."
        ),
    )


if __name__ == "__main__":
    main()
