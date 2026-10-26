"""Flix providers for the any-watch suite."""

from .idlix import IDLIXProvider
from .lk21 import LK21Provider
from .provider import FlixHQProvider
from .subdl import SubDLProvider

__all__ = [
    "FlixHQProvider",
    "IDLIXProvider",
    "LK21Provider",
    "SubDLProvider",
]
