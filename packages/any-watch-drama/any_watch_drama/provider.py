from __future__ import annotations

"""Backwards-compatible drama provider alias.

DramaCool is no longer reachable. The suite now exposes KissKH as the primary
drama API provider, so ``DramaProvider`` is kept as an alias for code that
imports the old name.
"""

from .kisskh import KissKHProvider


class DramaProvider(KissKHProvider):
    """Legacy alias: the old DramaCool provider now points at KissKH."""


__all__ = ["DramaProvider", "KissKHProvider"]
