"""Anime providers for the any-watch suite."""

from .anoboy import AnoBoyProvider
from .otakudesu import OtakuDesuProvider
from .provider import HiAnimeProvider
from .samehadaku import SamehadakuProvider

__all__ = [
    "AnoBoyProvider",
    "HiAnimeProvider",
    "OtakuDesuProvider",
    "SamehadakuProvider",
]
