from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .base import MediaItem

if TYPE_CHECKING:
    from .base import BaseProvider


async def pool_search(providers: list[BaseProvider], query: str) -> list[MediaItem]:
    """
    Run search across all providers concurrently via asyncio.gather().
    Tag each result with its provider & category, then combine into a flat list.
    """

    async def safe_search(provider: BaseProvider) -> list[MediaItem]:
        try:
            return await provider.search(query)
        except Exception as e:
            print(f"[{provider.name}] Search failed: {e}")
            return []

    results_per_provider = await asyncio.gather(
        *[safe_search(p) for p in providers]
    )

    combined: list[MediaItem] = []
    for results in results_per_provider:
        combined.extend(results)

    return combined
