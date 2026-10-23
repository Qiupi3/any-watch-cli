from __future__ import annotations

import re
import shutil
import subprocess
from typing import TYPE_CHECKING, Sequence

if TYPE_CHECKING:
    from any_watch_core.base import EpisodeItem


def prompt_selection(options: Sequence[str], prompt_text: str = "> ") -> str | None:
    """
    Interactive selection picker.
    Uses system 'fzf' if available via standard subprocess (zero external python dependencies),
    otherwise falls back to a clean numbered console menu.
    """
    if not options:
        return None

    # Try system fzf first
    if shutil.which("fzf"):
        try:
            proc = subprocess.Popen(
                ["fzf", "--prompt", f"{prompt_text} > ", "--height", "40%", "--reverse", "--cycle", "--no-sort"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            stdout, _ = proc.communicate(input="\n".join(options))
            chosen = stdout.strip()
            if chosen:
                return chosen
            return None
        except Exception:
            pass

    # Fallback to numbered console menu
    print(f"\n{prompt_text}")
    for i, opt in enumerate(options, 1):
        print(f"  [{i}] {opt}")

    while True:
        try:
            user_input = input(f"\nSelect (1-{len(options)}) [q to quit]: ").strip()
            if user_input.lower() in ("q", "quit", "exit", ""):
                return None
            idx = int(user_input) - 1
            if 0 <= idx < len(options):
                return options[idx]
            print(f"Please enter a number between 1 and {len(options)}.")
        except (ValueError, EOFError, KeyboardInterrupt):
            print()
            return None


def parse_episode_range(ep_input: str) -> list[int]:
    """Parse episode inputs like '1-3', '5', or '1,2,4' into a sorted list of integers."""
    ep_input = ep_input.strip()
    if not ep_input:
        return [1]

    results: set[int] = set()

    for part in ep_input.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            match = re.match(r"^(\d+)\s*-\s*(\d+)$", part)
            if match:
                start, end = int(match.group(1)), int(match.group(2))
                if start > end:
                    start, end = end, start
                for num in range(start, end + 1):
                    if num > 0:
                        results.add(num)
        else:
            try:
                num = int(part)
                if num > 0:
                    results.add(num)
            except ValueError:
                pass

    return sorted(results) if results else [1]


def _safe_int_ep(num_str: str | int | float) -> int | None:
    """Extract integer value from an episode number string (e.g. '01' -> 1, '40.0' -> 40)."""
    try:
        return int(float(str(num_str).strip()))
    except (ValueError, TypeError):
        m = re.search(r"(\d+)", str(num_str))
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                pass
    return None


def episode_sort_key(ep: EpisodeItem) -> tuple[int, float, str]:
    """
    Natural sort key for EpisodeItem based on season and numeric episode number.
    Ensures episodes like Episode 40 are never ordered between Episode 3 and Episode 5.
    """
    season = getattr(ep, "season", 1) or 1
    num_str = str(getattr(ep, "number", "")).strip()
    m = re.search(r"(\d+(?:\.\d+)?)", num_str)
    val = float(m.group(1)) if m else float("inf")
    return (season, val, num_str)


def resolve_selected_episodes(episodes: Sequence[EpisodeItem], ep_spec: str) -> list[EpisodeItem]:
    """
    Resolve episode items matching an episode specification like '1', '1-3', '2,5'.
    Matches first against the episode's actual number, or falls back to 1-based index in the list.
    """
    nums = parse_episode_range(ep_spec)
    if not nums:
        return []

    # 1. Match by numeric value of ep.number (e.g. ep.number == '1', '01', '1.0')
    num_set = set(nums)
    matched = [ep for ep in episodes if _safe_int_ep(ep.number) in num_set]
    if matched:
        return matched

    # 2. Fallback: match by 1-based index in the available episodes list
    by_idx = [episodes[i - 1] for i in nums if 1 <= i <= len(episodes)]
    return by_idx


def prompt_episode_selection(episodes: Sequence[EpisodeItem]) -> list[EpisodeItem]:
    """
    Unified interactive episode selector across all modules.
    - If fzf is available: opens interactive selector with multi-selection support.
    - If fzf is not available: prints numbered episode list and supports single number or range (e.g. '1', '1-3').
    """
    if not episodes:
        return []

    if len(episodes) == 1:
        return [episodes[0]]

    options = [ep.display_name for ep in episodes]

    # 1. Try fzf with multi-selection support
    if shutil.which("fzf"):
        try:
            proc = subprocess.Popen(
                [
                    "fzf",
                    "--prompt", "Select episode > ",
                    "--height", "40%",
                    "--reverse",
                    "--cycle",
                    "--multi",
                    "--no-sort",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
            stdout, _ = proc.communicate(input="\n".join(options))
            chosen_lines = [line.strip() for line in stdout.splitlines() if line.strip()]
            if chosen_lines:
                selected = []
                for line in chosen_lines:
                    if line in options:
                        selected.append(episodes[options.index(line)])
                if selected:
                    return selected
            return []
        except Exception:
            pass

    # 2. Numbered console menu fallback (supports single selection and range e.g. '1-3', '1,5')
    print(f"\nSelect episode ({len(episodes)} available):")
    for i, ep in enumerate(episodes, 1):
        print(f"  [{i}] {ep.display_name}")

    while True:
        try:
            user_input = input(
                f"\nSelect episode (1-{len(episodes)}, e.g. '1', '1-3', '1,5') [q to quit] [1]: "
            ).strip()
            if user_input.lower() in ("q", "quit", "exit"):
                return []
            if not user_input:
                return [episodes[0]]

            selected = resolve_selected_episodes(episodes, user_input)
            if selected:
                return selected
            print(f"Please enter valid episode number(s) between 1 and {len(episodes)}.")
        except (EOFError, KeyboardInterrupt):
            print()
            return []
