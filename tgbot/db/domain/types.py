"""Shared type aliases and domain constants for bot DB models."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

CefrLevel = Literal["a1", "a2", "b1", "b2", "c1"]
Pronunciation = Literal["us", "gb", "both"]
CardDialect = Literal["US", "GB", "BOTH"]

VALID_LEVELS: tuple[CefrLevel, ...] = ("a1", "a2", "b1", "b2", "c1")
VALID_PRONUNCIATIONS: frozenset[Pronunciation] = frozenset({"us", "gb", "both"})

DbRow = Mapping[str, object]


class DatabaseError(RuntimeError):
    """Raised when the bot database cannot be initialized safely."""
