"""User / admin row mappers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tgbot.db.models import (
    DialectPreference,
    UserRole,
    admin_user_from_row,
    user_from_row,
)
from tgbot.db.models.audience_stats import audience_stats_from_row


def _user_row(**overrides):
    row = {
        "telegram_user_id": 42,
        "username": "alice",
        "role": "user",
        "created_at": datetime(2026, 1, 1, tzinfo=UTC),
        "selected_levels": ("a1", "b1"),
        "dialect": "both",
        "is_active": True,
        "onboarding_completed": True,
        "paused_at": None,
        "blocked_at": None,
    }
    row.update(overrides)
    return row


def test_user_from_row_maps_settings_and_role() -> None:
    user = user_from_row(_user_row())
    assert user.telegram_user_id == 42
    assert user.role == UserRole.USER
    assert user.settings.selected_levels == ("a1", "b1")
    assert user.settings.dialect == DialectPreference.BOTH


def test_user_from_row_rejects_unknown_role() -> None:
    with pytest.raises(ValueError, match="unsupported user role"):
        user_from_row(_user_row(role="superuser"))


def test_admin_user_from_row_defaults_delivered_cards() -> None:
    admin = admin_user_from_row(_user_row(role="admin", delivered_cards=None))
    assert admin.role == UserRole.ADMIN
    assert admin.delivered_cards == 0


def test_user_from_row_maps_delivery_state() -> None:
    user = user_from_row(
        _user_row(is_active=False, onboarding_completed=True, dialect="gb")
    )
    assert user.settings.dialect == DialectPreference.GB
    assert user.is_active is False
    assert user.onboarding_completed is True


def test_audience_stats_from_row_skips_empty_dialects() -> None:
    stats = audience_stats_from_row(
        {
            "total_users": 10,
            "active_users": 4,
            "paused_users": 2,
            "blocked_users": 1,
            "new_today": 1,
            "new_week": 3,
            "new_month": 8,
        },
        ({"level": "a1", "users": 5}, {"level": "b1", "users": 2}),
        ({"dialect": "gb", "users": 3}, {"dialect": None, "users": 1}),
    )
    assert stats.total_users == 10
    assert stats.active_users == 4
    assert stats.levels == {"a1": 5, "b1": 2}
    assert stats.dialects == {"gb": 3}
