"""Map query rows onto user models."""

from __future__ import annotations

from typing import cast

from tgbot.db.mappers.values import (
    as_db_row,
    row_bool,
    row_datetime,
    row_int,
    row_optional_datetime,
    row_optional_str,
    row_str,
    row_str_sequence,
)
from tgbot.models import (
    VALID_DIALECT_PREFERENCES,
    VALID_ROLES,
    ActiveUser,
    AdminUser,
    DialectPreference,
    UserRole,
    UserSettings,
)


def normalize_dialect_preference(value: str) -> DialectPreference:
    normalized = value.lower()
    if normalized not in VALID_DIALECT_PREFERENCES:
        raise ValueError(f"unsupported dialect preference {value!r}")
    return cast(DialectPreference, normalized)


def _role_from_row(value: str | None) -> UserRole:
    role = (value or "user").lower()
    if role not in VALID_ROLES:
        raise ValueError(f"unsupported user role {value!r}")
    return cast(UserRole, role)


def _settings_from_row(data: object) -> UserSettings:
    row = as_db_row(data)
    raw_dialect = row_optional_str(row, "dialect")
    dialect: DialectPreference | None = None
    if raw_dialect is not None:
        dialect = normalize_dialect_preference(raw_dialect)

    return UserSettings(
        selected_levels=row_str_sequence(row, "selected_levels"),
        dialect=dialect,
    )


def user_from_row(row: object) -> ActiveUser:
    data = as_db_row(row)

    return ActiveUser(
        telegram_user_id=row_int(data, "telegram_user_id"),
        chat_id=row_int(data, "chat_id"),
        username=row_str(data, "username"),
        role=_role_from_row(row_optional_str(data, "role")),
        created_at=row_datetime(data, "created_at"),
        settings=_settings_from_row(data),
        is_active=row_bool(data, "is_active"),
        onboarding_completed=row_bool(data, "onboarding_completed"),
        paused_at=row_optional_datetime(data, "paused_at"),
        blocked_at=row_optional_datetime(data, "blocked_at"),
    )


def admin_user_from_row(row: object) -> AdminUser:
    data = as_db_row(row)
    base = user_from_row(data)

    return AdminUser(
        telegram_user_id=base.telegram_user_id,
        chat_id=base.chat_id,
        username=base.username,
        role=base.role,
        created_at=base.created_at,
        settings=base.settings,
        is_active=base.is_active,
        onboarding_completed=base.onboarding_completed,
        paused_at=base.paused_at,
        blocked_at=base.blocked_at,
        delivered_cards=row_int(data, "delivered_cards")
        if data["delivered_cards"] is not None
        else 0,
        last_successful_delivery=row_optional_datetime(
            data,
            "last_successful_delivery",
        ),
    )
