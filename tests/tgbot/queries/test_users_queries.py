"""User settings and pause/block rules."""

from __future__ import annotations

import pytest

from tests.support import requires_oald_database
from tgbot.db import Database
from tgbot.db.models import EnglishVarietyPreference


@requires_oald_database
@pytest.mark.asyncio
async def test_english_variety_change_preserves_pause(
    db: Database,
    onboarded_user: dict,
) -> None:
    user_id = onboarded_user["telegram_user_id"]
    await db.set_active(user_id, False)
    user = await db.set_english_variety(user_id, EnglishVarietyPreference.GB)

    assert user.is_active is False
    assert user.settings.english_variety == EnglishVarietyPreference.GB


@requires_oald_database
@pytest.mark.asyncio
async def test_block_keeps_paused_state(
    db: Database,
    onboarded_user: dict,
) -> None:
    user_id = onboarded_user["telegram_user_id"]
    await db.set_active(user_id, False)
    await db.deactivate_user(user_id)
    user = await db.upsert_user(telegram_user_id=user_id, username="integration")

    assert user.is_active is False
