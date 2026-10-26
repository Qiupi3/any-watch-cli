from __future__ import annotations

"""Shared CLI application flows for the master command and category modules."""

import argparse
import sys
from typing import Optional, Sequence

from .base import BaseProvider, BaseSubtitleProvider, MediaItem, SubtitleResult
from .catalog import (
    CATEGORIES,
    ProviderSpec,
    find_spec,
    format_catalog,
    get_category,
    get_specs,
    load_providers,
)
from .flow import _run, interactive_flow
from .pooler import pool_search
from .subtitles import download_subtitle
from .ui import prompt_selection

ALL_CATEGORY_LABEL = "🌐  All categories — search every site"


def _parse_common(parser: argparse.ArgumentParser) -> None:
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
    parser.add_argument(
        "--site",
        help="Use one site only (e.g. 'anoboy', 'lk21', 'kisskh')",
    )
    parser.add_argument(
        "--list-sites",
        action="store_true",
        help="List the available sites for this category and exit",
    )


def _prompt_category() -> Optional[str]:
    labels = [cat.menu_label for cat in CATEGORIES] + [ALL_CATEGORY_LABEL]
    chosen = prompt_selection(labels, "Choose a category")
    if not chosen:
        return None
    if chosen == ALL_CATEGORY_LABEL:
        return "all"
    return CATEGORIES[labels.index(chosen)].key


def _prompt_sites(category_key: str) -> Optional[list[ProviderSpec]]:
    category = get_category(category_key)
    if not category:
        return get_specs(category_key, kind="stream")

    specs = get_specs(category_key)
    all_label = (
        f"All {category.title} sites — search {len([s for s in specs if s.kind == 'stream'])} "
        f"streaming sites"
    )
    labels = [all_label] + [spec.menu_label for spec in specs]
    chosen = prompt_selection(labels, f"Select a {category.title} site")
    if not chosen:
        return None
    if chosen == all_label:
        return [spec for spec in specs if spec.kind == "stream"]
    return [specs[labels.index(chosen) - 1]]


def _prompt_query(label: str = "What would you like to watch?") -> Optional[str]:
    try:
        query = input(f"{label} ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    return query or None


def _resolve_site_argument(
    value: str, category_key: Optional[str] = None
) -> Optional[ProviderSpec]:
    spec = find_spec(value)
    if not spec:
        return None
    if category_key and spec.category != category_key:
        print(
            f"[!] '{value}' belongs to the {spec.category} category, "
            f"not {category_key}."
        )
        return None
    return spec


def _search(
    providers: Sequence[BaseProvider], query: str
) -> list[MediaItem]:
    if len(providers) == 1:
        print(f"\n[~] Searching '{query}' via {providers[0].name}...")
        try:
            return _run(providers[0].search(query))
        except Exception as exc:  # noqa: BLE001
            print(f"[{providers[0].name}] Search failed: {exc}")
            return []

    names = ", ".join(provider.name for provider in providers)
    print(f"\n[~] Searching '{query}' across {names}...")
    return _run(pool_search(list(providers), query))


def _run_subtitle_flow(
    provider: BaseSubtitleProvider, query: str, preferred: str = "ind"
) -> None:
    lang = "en" if preferred == "eng" else "id"
    print(f"\n[~] Searching subtitles for '{query}' via {provider.name}...")
    try:
        results: list[SubtitleResult] = _run(provider.search_subtitles(query, lang=lang))
    except Exception as exc:  # noqa: BLE001
        print(f"[!] Subtitle search failed: {exc}")
        sys.exit(1)

    if not results:
        print(f"[!] No subtitles found for '{query}'.")
        sys.exit(1)

    labels = [result.display_tag for result in results]
    chosen = prompt_selection(labels, f"Select a subtitle from {provider.name}")
    if not chosen:
        print("[!] Nothing selected, exiting.")
        sys.exit(0)

    result = results[labels.index(chosen)]
    print(f"\n[~] Downloading {result.language} subtitle...")
    try:
        path = _run(download_subtitle(result))
    except Exception as exc:  # noqa: BLE001
        print(f"[!] Download failed: {exc}")
        sys.exit(1)

    print(f"[+] Subtitle saved to: {path}")
    print("[i] Load it in your player with: mpv --sub-file=<path> <video>")


def _pick_and_play(
    args: argparse.Namespace,
    providers: Sequence[BaseProvider],
    query: str,
    single_episode_mode: bool,
) -> None:
    results = _search(providers, query)
    if not results:
        names = ", ".join(provider.name for provider in providers)
        print(f"[!] No results found for '{query}' across {names}.")
        sys.exit(1)

    labels = [item.display_tag for item in results]
    chosen = prompt_selection(labels, "Select what to watch")
    if not chosen:
        print("[!] Nothing selected, exiting.")
        sys.exit(0)

    selected: MediaItem = results[labels.index(chosen)]
    print(f"\n[+] Selected: {selected.title}  [{selected.provider}]")

    target_provider = next(
        (
            provider
            for provider in providers
            if provider.name.lower() == selected.provider.lower()
        ),
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
        single_episode_mode=single_episode_mode,
    )


def run_category_app(
    category_key: str,
    argv: Optional[list[str]] = None,
    prog: Optional[str] = None,
    description: str = "",
) -> None:
    parser = argparse.ArgumentParser(
        prog=prog or f"any-watch-{category_key}",
        description=description or f"Stream media from the {category_key} category.",
    )
    parser.add_argument("query", nargs="?", help="Title to search")
    _parse_common(parser)
    args = parser.parse_args(argv)

    if args.list_sites:
        print(format_catalog(category_key))
        return

    interactive = not args.query and sys.stdin.isatty()

    specs: list[ProviderSpec]
    if args.site:
        spec = _resolve_site_argument(args.site, category_key)
        if not spec:
            print(f"[!] Unknown site '{args.site}' for {category_key}.")
            print(format_catalog(category_key))
            sys.exit(1)
        specs = [spec]
    elif interactive:
        chosen_specs = _prompt_sites(category_key)
        if not chosen_specs:
            print("[!] No site selected, exiting.")
            sys.exit(0)
        specs = chosen_specs
    else:
        specs = get_specs(category_key, kind="stream")

    query = args.query
    if not query:
        query = _prompt_query("What would you like to watch?")
        if not query:
            parser.print_help()
            sys.exit(1)

    if len(specs) == 1 and specs[0].kind == "subtitle":
        loaded = load_providers(specs)
        if not loaded:
            sys.exit(1)
        _run_subtitle_flow(loaded[0][1], query, args.sub or "ind")
        return

    loaded = load_providers(specs)
    if not loaded:
        print("[!] No providers installed for this category.")
        sys.exit(1)

    providers = [provider for _spec, provider in loaded]
    _pick_and_play(
        args=args,
        providers=providers,
        query=query,
        single_episode_mode=False,
    )


def run_master_app(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        prog="any-watch",
        description=(
            "Universal terminal streaming suite — Flix, Anime & Drama 🎬"
        ),
        epilog=(
            "Subcommands:\n"
            "  any-watch flix <query>     🍿 Movies & Western TV\n"
            "  any-watch anime <query>    🎌 Anime Sub Indo\n"
            "  any-watch drama <query>    📺 KDrama & CDrama\n"
            "\n"
            "Interactive picker:\n"
            "  any-watch                  choose category → site → title\n"
            "  any-watch --pick \"frieren\" choose category and site first\n"
            "  any-watch --list-sites     show every category, site and mirror\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("query", nargs="?", help="What to watch")
    _parse_common(parser)
    parser.add_argument(
        "--provider",
        choices=["flix", "anime", "drama"],
        help="Limit search to one category",
    )
    parser.add_argument(
        "--pick",
        action="store_true",
        help="Always show the category/site picker, even with a query",
    )
    args = parser.parse_args(argv)

    if args.list_sites:
        print(format_catalog(args.provider))
        return

    if args.site:
        spec = _resolve_site_argument(args.site, args.provider)
        if not spec:
            print(f"[!] Unknown site '{args.site}'.")
            print(format_catalog(args.provider))
            sys.exit(1)
        specs = [spec]
    elif args.provider:
        if (args.pick or not args.query) and sys.stdin.isatty():
            chosen_specs = _prompt_sites(args.provider)
            if not chosen_specs:
                print("[!] No site selected, exiting.")
                sys.exit(0)
            specs = chosen_specs
        else:
            specs = get_specs(args.provider, kind="stream")
    elif args.pick or (not args.query and sys.stdin.isatty()):
        category_key = _prompt_category()
        if not category_key:
            print("[!] No category selected, exiting.")
            sys.exit(0)
        if category_key == "all":
            specs = get_specs(kind="stream")
        else:
            chosen_specs = _prompt_sites(category_key)
            if not chosen_specs:
                print("[!] No site selected, exiting.")
                sys.exit(0)
            specs = chosen_specs
    else:
        specs = get_specs(kind="stream")

    query = args.query
    if not query:
        query = _prompt_query()
        if not query:
            parser.print_help()
            sys.exit(1)

    if len(specs) == 1 and specs[0].kind == "subtitle":
        loaded = load_providers(specs)
        if not loaded:
            sys.exit(1)
        _run_subtitle_flow(loaded[0][1], query, args.sub or "ind")
        return

    loaded = load_providers(specs)
    if not loaded:
        print(
            "[!] No providers installed. Install any-watch-flix, "
            "any-watch-anime, or any-watch-drama."
        )
        sys.exit(1)

    providers = [provider for _spec, provider in loaded]
    _pick_and_play(
        args=args,
        providers=providers,
        query=query,
        single_episode_mode=True,
    )
