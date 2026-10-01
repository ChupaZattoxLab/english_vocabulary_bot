"""Card reservation and delivery history rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.support import requires_oald_database
from tgbot.db import Database
from tgbot.db.models import DialectPreference


@requires_oald_database
@pytest.mark.asyncio
async def test_cards_never_repeat_and_slot_is_idempotent(
    db: Database,
    onboarded_user: dict,
) -> None:
    user_id = onboarded_user["telegram_user_id"]
    first_slot = datetime.now(UTC)

    first = await db.reserve_card(user_id, first_slot)
    same_slot = await db.reserve_card(user_id, first_slot)
    second = await db.reserve_card(user_id, first_slot + timedelta(hours=1))
    exhausted = await db.reserve_card(user_id, first_slot + timedelta(hours=2))

    assert first is not None
    assert same_slot is None
    assert second is not None
    assert first.entry_id != second.entry_id
    assert exhausted is None


@requires_oald_database
@pytest.mark.asyncio
async def test_failed_delivery_does_not_consume_word_or_slot(
    db: Database,
    onboarded_user: dict,
) -> None:
    user_id = onboarded_user["telegram_user_id"]
    slot = datetime.now(UTC)
    first = await db.reserve_card(user_id, slot)
    second = await db.reserve_card(user_id, slot + timedelta(hours=1))
    assert first is not None and second is not None

    await db.finish_delivery(
        first.user_card_id,
        delivered=False,
        error_type="technical_error",
        error_message="boom",
    )
    await db.finish_delivery(
        second.user_card_id,
        delivered=True,
        telegram_message_id=1,
    )

    retry = await db.reserve_card(user_id, slot)
    assert retry is not None
    assert retry.entry_id == first.entry_id


@requires_oald_database
@pytest.mark.asyncio
async def test_paused_user_can_only_reserve_one_off_card(
    db: Database,
    onboarded_user: dict,
) -> None:
    user_id = onboarded_user["telegram_user_id"]
    await db.set_active(user_id, False)

    denied = await db.reserve_card(user_id, datetime.now(UTC))
    allowed = await db.reserve_card(user_id)

    assert denied is None
    assert allowed is not None


@requires_oald_database
@pytest.mark.asyncio
async def test_both_preference_hydrates_two_voices(
    db: Database,
    onboarded_user: dict,
) -> None:
    user_id = onboarded_user["telegram_user_id"]
    await db.set_dialect(user_id, DialectPreference.BOTH)

    card = await db.reserve_card(user_id, datetime.now(UTC))

    assert card is not None
    assert card.is_both
    assert card.us is not None and card.gb is not None
    assert card.us.ipa == "/us/"
    assert card.gb.ipa == "/gb/"
    assert card.us.audio.source_url in onboarded_user["us_audio_urls"]
    assert card.gb.audio.source_url in onboarded_user["gb_audio_urls"]
