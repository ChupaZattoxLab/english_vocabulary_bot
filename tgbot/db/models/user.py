"""User identity, settings, and delivery-state models."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, cast

from tgbot.db.models.types import (
    VALID_DIALECT_PREFERENCES,
    VALID_ROLES,
    DialectPreference,
    UserRole,
)


@dataclass(frozen=True)
class UserSettings:
    selected_levels: tuple[str, ...]
    dialect: DialectPreference | None


@dataclass(frozen=True)
class User:
    telegram_user_id: int
    username: str
    role: UserRole
    created_at: datetime


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


@dataclass(frozen=True)
class CardDeliveryPrefs:
    """Subset of bot_users columns checked before reserving a card."""
    selected_levels: tuple[str, ...]
    dialect: DialectPreference | None
    is_active: bool
    onboarding_completed: bool


def active_user_from_row(row: object) -> ActiveUser:
    """Like ravenspedia ``table_to_response_form``: mapping row → ActiveUser."""
    data = dict(cast(Mapping[Any, Any], row))
    role = str(data.get("role") or "user").lower()
    if role not in VALID_ROLES:
        raise ValueError(f"unsupported user role {data.get('role')!r}")

    return ActiveUser(
        telegram_user_id=int(data["telegram_user_id"]),
        username=str(data.get("username") or ""),
        role=cast(UserRole, role),
        created_at=data["created_at"],
        settings=user_settings_from_row(data),
        is_active=bool(data["is_active"]),
        onboarding_completed=bool(data["onboarding_completed"]),
        paused_at=data.get("paused_at"),
        blocked_at=data.get("blocked_at"),
    )


def admin_user_from_row(row: object) -> AdminUser:
    data = dict(cast(Mapping[Any, Any], row))
    base = active_user_from_row(data)
    delivered = data.get("delivered_cards")

    return AdminUser(
        telegram_user_id=base.telegram_user_id,
        username=base.username,
        role=base.role,
        created_at=base.created_at,
        settings=base.settings,
        is_active=base.is_active,
        onboarding_completed=base.onboarding_completed,
        paused_at=base.paused_at,
        blocked_at=base.blocked_at,
        delivered_cards=0 if delivered is None else int(delivered),
        last_successful_delivery=data.get("last_successful_delivery"),
    )


def user_settings_from_row(row: Mapping[Any, Any]) -> UserSettings:
    raw_dialect = row.get("dialect")
    dialect: DialectPreference | None = None
    if raw_dialect is not None:
        normalized = str(raw_dialect).lower()
        if normalized not in VALID_DIALECT_PREFERENCES:
            raise ValueError(f"unsupported dialect preference {raw_dialect!r}")
        dialect = cast(DialectPreference, normalized)

    levels = row.get("selected_levels") or ()
    return UserSettings(
        selected_levels=tuple(str(level) for level in levels),
        dialect=dialect,
    )


def card_delivery_prefs_from_row(row: object) -> CardDeliveryPrefs:
    data = dict(cast(Mapping[Any, Any], row))
    raw_dialect = data.get("dialect")
    dialect: DialectPreference | None = None
    if raw_dialect is not None:
        dialect = cast(DialectPreference, str(raw_dialect).lower())

    levels = data.get("selected_levels") or ()
    return CardDeliveryPrefs(
        selected_levels=tuple(str(level) for level in levels),
        dialect=dialect,
        is_active=bool(data.get("is_active")),
        onboarding_completed=bool(data.get("onboarding_completed")),
    )
