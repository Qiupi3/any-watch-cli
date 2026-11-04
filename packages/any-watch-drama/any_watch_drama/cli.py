#!/usr/bin/env python3
"""any-watch-drama — KDrama/CDrama from KissKH, NaraShika, Nontongo, and more."""
from __future__ import annotations

from any_watch_core.app import run_category_app


def main(argv: list[str] | None = None) -> None:
    run_category_app(
        "drama",
        argv,
        prog="any-watch-drama",
        description=(
            "Stream Korean and Chinese dramas 📺 — KissKH, NaraShika, "
            "Nontongo, DramaSerial and Drakorindo."
        ),
    )


if __name__ == "__main__":
    main()
