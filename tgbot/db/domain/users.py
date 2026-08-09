"""User-facing bot account models."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BotUser:
    telegram_user_id: int
    chat_id: int
    username: str
    first_name: str
    selected_levels: tuple[str, ...]
    pronunciation: str | None
    onboarding_completed: bool
    is_active: bool


@dataclass(frozen=True)
class ActiveUser:
    telegram_user_id: int
    chat_id: int
