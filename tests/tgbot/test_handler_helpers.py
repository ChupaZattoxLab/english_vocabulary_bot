"""Handler helper pure functions."""

from __future__ import annotations

from datetime import UTC, datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from tests.tgbot.factories import make_admin_user
from tgbot.bot_config import BotConfig, ScheduleSettings
from tgbot.db.models import ActiveUser, DialectPreference, UserRole, UserSettings
from tgbot.handlers.admin import delivery_state, local_day_bounds
from tgbot.handlers.helpers import command_arguments, format_levels, format_number
from tgbot.handlers.user import user_settings_text
from tgbot.localization import locale


def test_format_number_uses_spaces() -> None:
    assert format_number(1_234_567) == "1 234 567"


def test_format_levels_uppercases_or_empty() -> None:
    assert format_levels(("a1", "b2"), "none") == "A1, B2"
    assert format_levels((), "none") == "none"


def test_command_arguments_takes_rest_of_message() -> None:
    assert command_arguments(SimpleNamespace(text="/user 123")) == "123"
    assert command_arguments(SimpleNamespace(text="/user")) == ""
    assert command_arguments(SimpleNamespace(text=None)) == ""


def test_delivery_state_priority_blocked_then_paused() -> None:
    assert (
        delivery_state(make_admin_user(blocked_at=datetime.now(UTC)))
        == locale.admin.delivery_blocked
    )
    assert (
        delivery_state(make_admin_user(is_active=False, paused_at=datetime.now(UTC)))
        == locale.admin.delivery_paused
    )
    assert delivery_state(make_admin_user()) == locale.admin.delivery_active


def test_local_day_bounds_are_timezone_aware() -> None:
    schedule = ScheduleSettings(
        timezone=ZoneInfo("Europe/Moscow"),
        send_times=(time(13, 0),),
        text="13:00",
        poll_seconds=20,
        delivery_concurrency=5,
        grace_minutes=60,
    )
    config = BotConfig(
        bot_token="t",
        db_url="postgresql+psycopg://localhost/x",
        db_pool_size=1,
        schedule=schedule,
    )
    local_now, today_start = local_day_bounds(config)
    assert local_now.tzinfo is not None
    assert today_start.tzinfo is UTC
    assert today_start.hour == 0 or today_start.utcoffset() is not None


def test_user_settings_text_includes_levels_and_schedule() -> None:
    user = ActiveUser(
        telegram_user_id=1,
        username="u",
        role=UserRole.USER,
        created_at=datetime.now(UTC),
        settings=UserSettings(
            selected_levels=("a1",),
            dialect=DialectPreference.US,
        ),
        is_active=True,
        onboarding_completed=True,
        paused_at=None,
        blocked_at=None,
    )
    schedule = ScheduleSettings(
        timezone=ZoneInfo("Europe/Moscow"),
        send_times=(time(13, 0), time(20, 0)),
        text="13:00, 20:00 (Europe/Moscow)",
        poll_seconds=20,
        delivery_concurrency=5,
        grace_minutes=60,
    )
    config = BotConfig(
        bot_token="t",
        db_url="postgresql+psycopg://localhost/x",
        db_pool_size=1,
        schedule=schedule,
    )
    text = user_settings_text(user, config)
    assert "A1" in text
    assert "US" in text
    assert "13:00, 20:00" in text
