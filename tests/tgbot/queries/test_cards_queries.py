"""Card reservation and delivery history rules."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from tests.support import requires_oald_database
from tgbot.db import Database
from tgbot.db.models import EnglishVariety, EnglishVarietyPreference
from tgbot.db.sync import sync_connection
from tgbot.db.tables import (
    oald_audio_files,
    oald_audio_variants,
    oald_entries,
    oald_entry_audio_sources,
)
from tgbot.db.types import AudioConversionStatus, AudioDownloadStatus


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
    await db.set_english_variety(user_id, EnglishVarietyPreference.BOTH)

    card = await db.reserve_card(user_id, datetime.now(UTC))

    assert card is not None
    assert card.is_both
    assert card.us is not None and card.gb is not None
    assert card.us.ipa == "/us/"
    assert card.gb.ipa == "/gb/"
    assert card.us.audio.source_url in onboarded_user["us_audio_urls"]
    assert card.gb.audio.source_url in onboarded_user["gb_audio_urls"]


@requires_oald_database
@pytest.mark.asyncio
async def test_pronunciation_choice_uses_later_tracks(
    db: Database,
    onboarded_user: dict,
) -> None:
    add_second_pronunciations(
        onboarded_user["db_url"],
        onboarded_user["entry_ids"],
        onboarded_user["audio_urls"],
    )
    user_id = onboarded_user["telegram_user_id"]
    slot = datetime.now(UTC)
    await db.set_english_variety(user_id, EnglishVarietyPreference.BOTH)

    both = await db.reserve_card(user_id, slot)

    assert both is not None
    assert both.us is not None and both.gb is not None
    assert both.us.ipa == "/other-us/"
    assert both.gb.ipa == "/same/"
    assert both.us.audio.audio_data == b"US-ALT"
    assert both.gb.audio.source_url in onboarded_user["gb_audio_urls"]
    assert [variant.english_variety for variant in both.variants()] == [
        EnglishVariety.US,
        EnglishVariety.GB,
    ]

    await db.set_english_variety(user_id, EnglishVarietyPreference.US)
    single = await db.reserve_card(user_id, slot + timedelta(hours=1))

    assert single is not None
    assert single.gb is None
    assert [variant.ipa for variant in single.variants()] == ["/same/"]
    assert single.us is not None
    assert single.us.audio.source_url in onboarded_user["us_audio_urls"]

    preview = await db.get_preview_card(both.entry_id)
    assert preview is not None
    gb_view = preview.for_preference(EnglishVarietyPreference.GB)
    both_view = preview.for_preference(EnglishVarietyPreference.BOTH)
    assert [variant.ipa for variant in gb_view.variants()] == ["/same/"]
    assert both_view.us is not None and both_view.us.ipa == "/other-us/"
    assert both_view.gb is not None and both_view.gb.ipa == "/same/"


def add_second_pronunciations(
    db_url: str,
    entry_ids: list[uuid.UUID],
    audio_urls: list[str],
) -> None:
    """Position 0 stays /same/ on both varieties; position 1 US differs."""
    with sync_connection(db_url) as connection:
        for entry_id in entry_ids:
            connection.execute(
                sa.update(oald_entries)
                .where(oald_entries.c.id == entry_id)
                .values(
                    ipa_us=["/same/", "/other-us/"],
                    ipa_gb=["/same/", "/other-gb/"],
                )
            )
            for variety, blob in (
                (EnglishVariety.US, b"US-ALT"),
                (EnglishVariety.GB, b"GB-ALT"),
            ):
                source_url = f"https://audio.example/bot/alt/{entry_id}/{variety}.ogg"
                audio_urls.append(source_url)
                connection.execute(
                    sa.insert(oald_audio_files).values(
                        source_url=source_url,
                        audio_data=blob,
                        content_type="audio/ogg",
                        filename=f"{variety}.ogg",
                        size_bytes=len(blob),
                        sha256="2" * 64,
                        download_status=AudioDownloadStatus.DOWNLOADED,
                    )
                )
                connection.execute(
                    sa.insert(oald_entry_audio_sources).values(
                        entry_id=entry_id,
                        english_variety=variety,
                        source_position=1,
                        source_url=source_url,
                    )
                )
                connection.execute(
                    sa.insert(oald_audio_variants).values(
                        source_url=source_url,
                        source_sha256="2" * 64,
                        audio_data=blob,
                        content_type="audio/ogg",
                        filename=f"{variety}.voice.ogg",
                        size_bytes=len(blob),
                        sha256="3" * 64,
                        conversion_status=AudioConversionStatus.PREPARED,
                    )
                )
