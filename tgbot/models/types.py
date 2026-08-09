"""Shared type aliases and model constants."""

from __future__ import annotations

from typing import Final, Literal, get_args

CefrLevel = Literal["a1", "a2", "b1", "b2", "c1"]
Dialect = Literal["us", "gb"]
DialectPreference = Literal["us", "gb", "both"]
UserRole = Literal["user", "admin"]

VALID_LEVELS: Final[tuple[CefrLevel, ...]] = get_args(CefrLevel)
VALID_DIALECTS: Final[tuple[Dialect, ...]] = get_args(Dialect)
VALID_DIALECT_PREFERENCES: Final[tuple[DialectPreference, ...]] = get_args(
    DialectPreference
)
VALID_ROLES: Final[tuple[UserRole, ...]] = get_args(UserRole)
