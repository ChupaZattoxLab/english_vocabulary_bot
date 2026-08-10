"""User / admin row mappers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tgbot.db.models import (
    DialectPreference,
    UserRole,
    active_user_from_row,
    admin_user_from_row,
    card_delivery_prefs_from_row,
)
from tgbot.db.models.word_match import word_match_from_row


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


def test_active_user_from_row_maps_settings_and_role() -> None:
    user = active_user_from_row(_user_row())
    assert user.telegram_user_id == 42
    assert user.role == UserRole.USER
    assert user.settings.selected_levels == ("a1", "b1")
    assert user.settings.dialect == DialectPreference.BOTH


def test_active_user_from_row_rejects_unknown_role() -> None:
    with pytest.raises(ValueError, match="unsupported user role"):
        active_user_from_row(_user_row(role="superuser"))


def test_admin_user_from_row_defaults_delivered_cards() -> None:
    admin = admin_user_from_row(_user_row(role="admin", delivered_cards=None))
    assert admin.role == UserRole.ADMIN
    assert admin.delivered_cards == 0


def test_card_delivery_prefs_from_row() -> None:
    prefs = card_delivery_prefs_from_row(
        _user_row(is_active=False, onboarding_completed=True, dialect="gb")
    )
    assert prefs.dialect == DialectPreference.GB
    assert prefs.is_active is False
    assert prefs.onboarding_completed is True


def test_word_match_from_row() -> None:
    match = word_match_from_row(
        {
            "id": 9,
            "word_us": "color",
            "word_gb": "colour",
            "lexical_category": "noun",
            "cefr": "b2",
        }
    )
    assert match.id == 9
    assert match.cefr == "b2"
