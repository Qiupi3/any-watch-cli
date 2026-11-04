from __future__ import annotations

import asyncio
from difflib import SequenceMatcher
import re
from typing import TYPE_CHECKING

from .base import MediaItem, MediaType

if TYPE_CHECKING:
    from .base import BaseProvider


def _calculate_relevance(item: MediaItem, query: str) -> float:
    """Calculate match relevance score (0.0 - 100.0) between item and query."""
    q = query.strip().lower()
    t = item.title.strip().lower()

    # Clean title removing trailing years like (2021) or (2019)
    clean_t = re.sub(r"\s*\(\d{4}\)", "", t).strip()

    # 1. Exact match gets highest score
    if clean_t == q or t == q:
        score = 100.0
    elif clean_t.startswith(q) or t.startswith(q):
        score = 90.0 + (len(q) / max(len(clean_t), 1)) * 5.0
    elif q in clean_t or q in t:
        score = 80.0 + (len(q) / max(len(clean_t), 1)) * 5.0
    else:
        # Fuzzy match using SequenceMatcher
        ratio = SequenceMatcher(None, q, clean_t).ratio()
        score = ratio * 75.0

    # Boost drama provider for drama content when exact match
    if item.media_type == MediaType.DRAMA and (clean_t == q or q in clean_t):
        score += 2.0

    return score


async def pool_search(providers: list[BaseProvider], query: str) -> list[MediaItem]:
    """
    Run search across all providers concurrently via asyncio.gather().
    Sort results by relevance to the query rather than arbitrary provider order.
    """

    async def safe_search(provider: BaseProvider) -> list[MediaItem]:
        try:
            return await provider.search(query)
        except Exception as e:
            err_msg = str(e) or type(e).__name__
            print(f"[{provider.name}] Search failed: {err_msg}")
            return []

    results_per_provider = await asyncio.gather(
        *[safe_search(p) for p in providers]
    )

    combined: list[MediaItem] = []
    for results in results_per_provider:
        combined.extend(results)

    # Sort by relevance descending
    combined.sort(key=lambda it: _calculate_relevance(it, query), reverse=True)

    return combined
