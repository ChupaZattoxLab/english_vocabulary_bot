"""Postgres fixtures for tgbot integration tests (schema via Alembic once)."""

from __future__ import annotations

import asyncio
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from tests.support import TEST_OALD_DATABASE_URL
from tgbot.db import Database
from tgbot.db.models import CefrLevel, EnglishVarietyPreference
from tgbot.db.postgres import destroy_database, ensure_database_exists
from tgbot.db.tables import (
    bot_scheduler_runs,
    bot_users,
    oald_audio_files,
    oald_audio_variants,
    oald_entries,
    oald_entry_audio_sources,
)
from tgbot.db.types import (
    AudioConversionStatus,
    AudioDownloadStatus,
    new_id,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
GRACE_MINUTES = 60


@pytest.fixture(scope="module")
def migrated_db_url() -> Iterator[str]:
    if not TEST_OALD_DATABASE_URL:
        pytest.skip("TEST_OALD_DATABASE_URL is not set")

    db_name = f"vocab_bot_{uuid.uuid4().hex}"
    base_url = make_url(TEST_OALD_DATABASE_URL)
    db_url = base_url.set(database=db_name).render_as_string(hide_password=False)

    asyncio.run(ensure_database_exists(db_url))

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    with patch.dict(os.environ, {"OALD_DATABASE_URL": db_url}):
        import tgbot.secrets as app_secrets

        app_secrets.secrets = app_secrets.Secrets.load()
        command.upgrade(config, "head")

    yield db_url

    asyncio.run(destroy_database(db_url))


@pytest_asyncio.fixture
async def db(migrated_db_url: str) -> AsyncIterator[Database]:
    database = Database(migrated_db_url, pool_size=2)
    await database.open()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def onboarded_user(db: Database) -> AsyncIterator[dict]:
    """Seed two C1 entries with US+GB prepared voice, plus an onboarded user."""
    suffix = uuid.uuid4().hex
    telegram_user_id = int("8" + suffix[:15], 16) % 8_000_000_000 + 1
    definition_urls = [
        f"https://dictionary.example/bot/{suffix}/one",
        f"https://dictionary.example/bot/{suffix}/two",
    ]
    us_audio_urls = [
        f"https://audio.example/bot/{suffix}/one.ogg",
        f"https://audio.example/bot/{suffix}/two.ogg",
    ]
    gb_audio_urls = [
        f"https://audio.example/bot/{suffix}/one-gb.ogg",
        f"https://audio.example/bot/{suffix}/two-gb.ogg",
    ]
    audio_urls = [*us_audio_urls, *gb_audio_urls]
    entry_ids: list[uuid.UUID] = []

    blob = b"OggS-bot-test"
    voice = b"OggS-OpusHead-bot-test"
    async with db.begin() as connection:
        for index in range(2):
            entry_id = new_id()
            await connection.execute(
                sa.insert(oald_entries).values(
                    id=entry_id,
                    word_us=f"bot-test-{suffix}-{index}",
                    word_gb=f"bot-test-{suffix}-{index}",
                    lexical_category="noun",
                    cefr=CefrLevel.C1,
                    definition_url_oxford=definition_urls[index],
                    definition_url_cambridge="",
                    ipa_us=["/us/"],
                    ipa_gb=["/gb/"],
                    definition=f"Definition {index}",
                    example=f"Example {index}",
                    audio_source_us=[us_audio_urls[index]],
                    audio_source_gb=[gb_audio_urls[index]],
                    translations=[f"перевод {index}"],
                )
            )
            entry_ids.append(entry_id)
            for english_variety, audio_url in (
                ("us", us_audio_urls[index]),
                ("gb", gb_audio_urls[index]),
            ):
                await connection.execute(
                    sa.insert(oald_audio_files).values(
                        source_url=audio_url,
                        audio_data=blob,
                        content_type="audio/ogg",
                        filename=f"test-{index}-{english_variety}.ogg",
                        size_bytes=len(blob),
                        sha256="0" * 64,
                        download_status=AudioDownloadStatus.DOWNLOADED,
                    )
                )
                await connection.execute(
                    sa.insert(oald_entry_audio_sources).values(
                        entry_id=entry_id,
                        english_variety=english_variety,
                        source_position=0,
                        source_url=audio_url,
                    )
                )
                await connection.execute(
                    sa.insert(oald_audio_variants).values(
                        source_url=audio_url,
                        source_sha256="0" * 64,
                        audio_data=voice,
                        content_type="audio/ogg",
                        filename=f"test-{index}-{english_variety}.voice.ogg",
                        size_bytes=len(voice),
                        sha256="1" * 64,
                        conversion_status=AudioConversionStatus.PREPARED,
                    )
                )

    await db.upsert_user(telegram_user_id=telegram_user_id, username="integration")
    await db.toggle_level(telegram_user_id, CefrLevel.C1)
    await db.set_english_variety(telegram_user_id, EnglishVarietyPreference.US)

    ctx = {
        "telegram_user_id": telegram_user_id,
        "entry_ids": entry_ids,
        "us_audio_urls": us_audio_urls,
        "gb_audio_urls": gb_audio_urls,
        "audio_urls": audio_urls,
        "scheduler_slots": [],
    }
    yield ctx

    async with db.begin() as connection:
        await connection.execute(
            sa.delete(bot_users).where(bot_users.c.telegram_user_id == telegram_user_id)
        )
        if ctx["scheduler_slots"]:
            await connection.execute(
                sa.delete(bot_scheduler_runs).where(
                    bot_scheduler_runs.c.scheduled_slot.in_(ctx["scheduler_slots"])
                )
            )
        await connection.execute(
            sa.delete(oald_entries).where(oald_entries.c.id.in_(entry_ids))
        )
        await connection.execute(
            sa.delete(oald_audio_files).where(
                oald_audio_files.c.source_url.in_(audio_urls),
                ~sa.exists(
                    sa.select(sa.literal(1)).where(
                        oald_entry_audio_sources.c.source_url
                        == oald_audio_files.c.source_url
                    )
                ),
            )
        )
