from __future__ import annotations

import re
import shutil
import subprocess
from typing import Sequence


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
                ["fzf", "--prompt", f"{prompt_text} > ", "--height", "40%", "--reverse", "--cycle"],
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
