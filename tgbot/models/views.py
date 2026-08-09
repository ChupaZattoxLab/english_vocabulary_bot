"""Read-model / query projection dataclasses."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AudienceStats:
    total_users: int
    active_users: int
    paused_users: int
    blocked_users: int
    new_today: int
    new_week: int
    new_month: int
    levels: dict[str, int]
    dialects: dict[str, int]


@dataclass(frozen=True)
class WordMatch:
    id: int
    word_us: str
    word_gb: str
    lexical_category: str
    cefr: str
