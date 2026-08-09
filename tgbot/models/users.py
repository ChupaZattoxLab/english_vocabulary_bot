"""User identity, settings, and delivery-state models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from tgbot.models.types import DialectPreference, UserRole


@dataclass(frozen=True)
class User:
    telegram_user_id: int
    chat_id: int
    username: str
    role: UserRole
    created_at: datetime


@dataclass(frozen=True)
class UserSettings:
    selected_levels: tuple[str, ...]
    dialect: DialectPreference | None


@dataclass(frozen=True)
class ActiveUser(User):
    settings: UserSettings
    is_active: bool
    onboarding_completed: bool
    paused_at: datetime | None
    blocked_at: datetime | None


@dataclass(frozen=True)
class AdminUser(ActiveUser):
    delivered_cards: int
    last_successful_delivery: datetime | None
