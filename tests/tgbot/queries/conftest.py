"""Postgres fixtures for tgbot integration tests (schema via Alembic once)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from psycopg.types.json import Jsonb
from sqlalchemy.engine import make_url

from tests.support import TEST_OALD_DATABASE_URL
from tgbot.db import Database
from tgbot.db.models import CefrLevel, DialectPreference
from tgbot.db.sync import (
    destroy_database,
    ensure_database_exists,
    sync_connection,
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

    ensure_database_exists(db_url)

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    with patch.dict(os.environ, {"OALD_DATABASE_URL": db_url}):
        import tgbot.secrets as app_secrets

        app_secrets.secrets = app_secrets.Secrets.load()
        command.upgrade(config, "head")

    yield db_url

    destroy_database(db_url)


@pytest_asyncio.fixture
async def db(migrated_db_url: str) -> AsyncIterator[Database]:
    database = Database(migrated_db_url, pool_size=2)
    await database.open()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def onboarded_user(db: Database, migrated_db_url: str) -> AsyncIterator[dict]:
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
    entry_ids: list[int] = []

    with sync_connection(migrated_db_url) as connection:
        raw = connection.connection.driver_connection
        assert raw is not None
        with raw.cursor() as cursor:
            for index in range(2):
                cursor.execute(
                    """
                    INSERT INTO oald_entries (
                        word_us, word_gb, lexical_category, cefr,
                        definition_url_oxford, definition_url_cambridge,
                        ipa_us, ipa_gb, definition, example,
                        audio_source_us, audio_source_gb, translations
                    ) VALUES (
                        %s, %s, 'noun', 'c1', %s, '',
                        ARRAY['/us/'], ARRAY['/gb/'], %s, %s,
                        ARRAY[%s], ARRAY[%s], %s
                    ) RETURNING id
                    """,
                    (
                        f"bot-test-{suffix}-{index}",
                        f"bot-test-{suffix}-{index}",
                        definition_urls[index],
                        f"Definition {index}",
                        f"Example {index}",
                        us_audio_urls[index],
                        gb_audio_urls[index],
                        Jsonb({"ru": {"main": f"перевод {index}", "also": []}}),
                    ),
                )
                entry_id = int(cursor.fetchone()[0])
                entry_ids.append(entry_id)
                for dialect, audio_url in (
                    ("us", us_audio_urls[index]),
                    ("gb", gb_audio_urls[index]),
                ):
                    cursor.execute(
                        """
                        INSERT INTO oald_audio_files (
                            source_url, audio_data, content_type, filename,
                            size_bytes, sha256, download_status
                        ) VALUES (
                            %s, %s, 'audio/ogg', %s, %s, %s, 'downloaded'
                        )
                        """,
                        (
                            audio_url,
                            b"OggS-bot-test",
                            f"test-{index}-{dialect}.ogg",
                            len(b"OggS-bot-test"),
                            "0" * 64,
                        ),
                    )
                    cursor.execute(
                        """
                        INSERT INTO oald_entry_audio_sources (
                            entry_id, dialect, source_position, source_url
                        ) VALUES (%s, %s, 0, %s)
                        """,
                        (entry_id, dialect, audio_url),
                    )
                    cursor.execute(
                        """
                        INSERT INTO oald_audio_variants (
                            source_url, variant_type, source_sha256,
                            audio_data, content_type, filename, size_bytes,
                            sha256, conversion_status
                        ) VALUES (
                            %s, 'telegram_voice_opus', %s,
                            %s, 'audio/ogg', %s, %s, %s, 'prepared'
                        )
                        """,
                        (
                            audio_url,
                            "0" * 64,
                            b"OggS-OpusHead-bot-test",
                            f"test-{index}-{dialect}.voice.ogg",
                            len(b"OggS-OpusHead-bot-test"),
                            "1" * 64,
                        ),
                    )

    await db.upsert_user(telegram_user_id=telegram_user_id, username="integration")
    await db.toggle_level(telegram_user_id, CefrLevel.C1)
    await db.set_dialect(telegram_user_id, DialectPreference.US)

    ctx = {
        "telegram_user_id": telegram_user_id,
        "entry_ids": entry_ids,
        "us_audio_urls": us_audio_urls,
        "gb_audio_urls": gb_audio_urls,
        "audio_urls": audio_urls,
        "scheduler_slots": [],
        "db_url": migrated_db_url,
    }
    yield ctx

    with sync_connection(migrated_db_url) as connection:
        raw = connection.connection.driver_connection
        assert raw is not None
        with raw.cursor() as cursor:
            cursor.execute(
                "DELETE FROM bot_users WHERE telegram_user_id = %s",
                (telegram_user_id,),
            )
            if ctx["scheduler_slots"]:
                cursor.execute(
                    "DELETE FROM bot_scheduler_runs WHERE scheduled_slot = ANY(%s)",
                    (ctx["scheduler_slots"],),
                )
            cursor.execute(
                "DELETE FROM oald_entries WHERE id = ANY(%s)",
                (entry_ids,),
            )
            cursor.execute(
                """
                DELETE FROM oald_audio_files
                WHERE source_url = ANY(%s)
                  AND NOT EXISTS (
                      SELECT 1 FROM oald_entry_audio_sources
                      WHERE oald_entry_audio_sources.source_url =
                            oald_audio_files.source_url
                  )
                """,
                (audio_urls,),
            )
