"""Admin panel summary and lookup models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AdminUsersSummary:
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
class AdminUserDetail:
    telegram_user_id: int
    chat_id: int
    username: str
    first_name: str
    selected_levels: tuple[str, ...]
    pronunciation: str | None
    onboarding_completed: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_delivery_at: datetime | None
    paused_at: datetime | None
    blocked_at: datetime | None
    delivered_cards: int
    last_successful_delivery: datetime | None


@dataclass(frozen=True)
class AdminContentSummary:
    ready_entries: int


@dataclass(frozen=True)
class AdminWordMatch:
    id: int
    word_us: str
    word_gb: str
    lexical_category: str
    cefr: str
