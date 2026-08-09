import os
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from psycopg import sql
from psycopg.types.json import Jsonb
from sqlalchemy.engine import make_url

from tests.support import TEST_OALD_DATABASE_URL, requires_oald_database
from tgbot.db import Database
from tgbot.db.sync import sync_connection

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@requires_oald_database
class BotDatabaseIntegrationTests(unittest.IsolatedAsyncioTestCase):
    """Run against an empty migrated database so CEFR pools stay isolated."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.db_name = f"vocab_bot_{uuid.uuid4().hex}"
        base_url = make_url(TEST_OALD_DATABASE_URL)
        cls.admin_url = base_url.set(database="postgres").render_as_string(
            hide_password=False
        )
        cls.db_url = base_url.set(database=cls.db_name).render_as_string(
            hide_password=False
        )

        with sync_connection(cls.admin_url, autocommit=True) as connection:
            raw = connection.connection.driver_connection
            assert raw is not None
            with raw.cursor() as cursor:
                cursor.execute(
                    sql.SQL("CREATE DATABASE {}").format(
                        sql.Identifier(cls.db_name)
                    )
                )

        config = Config(str(PROJECT_ROOT / "alembic.ini"))
        with patch.dict(os.environ, {"OALD_DATABASE_URL": cls.db_url}):
            import tgbot.secrets as app_secrets

            app_secrets.secrets = app_secrets.Secrets.load()
            command.upgrade(config, "head")

    @classmethod
    def tearDownClass(cls) -> None:
        with sync_connection(cls.admin_url, autocommit=True) as connection:
            raw = connection.connection.driver_connection
            assert raw is not None
            with raw.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT pg_terminate_backend(pid)
                    FROM pg_stat_activity
                    WHERE datname = %s
                      AND pid <> pg_backend_pid()
                    """,
                    (cls.db_name,),
                )
                cursor.execute(
                    sql.SQL("DROP DATABASE IF EXISTS {}").format(
                        sql.Identifier(cls.db_name)
                    )
                )

    async def asyncSetUp(self) -> None:
        self.suffix = uuid.uuid4().hex
        self.telegram_user_id = int("8" + self.suffix[:15], 16) % 8_000_000_000 + 1
        self.definition_urls = [
            f"https://dictionary.example/bot/{self.suffix}/one",
            f"https://dictionary.example/bot/{self.suffix}/two",
        ]
        self.us_audio_urls = [
            f"https://audio.example/bot/{self.suffix}/one.ogg",
            f"https://audio.example/bot/{self.suffix}/two.ogg",
        ]
        self.gb_audio_urls = [
            f"https://audio.example/bot/{self.suffix}/one-gb.ogg",
            f"https://audio.example/bot/{self.suffix}/two-gb.ogg",
        ]
        self.audio_urls = [*self.us_audio_urls, *self.gb_audio_urls]
        self.entry_ids: list[int] = []
        self.scheduler_slots: list[datetime] = []
        self.db = Database(self.db_url, pool_size=2)
        await self.db.open()
        with sync_connection(self.db_url) as connection:
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
                            f"bot-test-{self.suffix}-{index}",
                            f"bot-test-{self.suffix}-{index}",
                            self.definition_urls[index],
                            f"Definition {index}",
                            f"Example {index}",
                            self.us_audio_urls[index],
                            self.gb_audio_urls[index],
                            Jsonb({"ru": {"main": f"перевод {index}", "also": []}}),
                        ),
                    )
                    entry_id = int(cursor.fetchone()[0])
                    self.entry_ids.append(entry_id)
                    for dialect, audio_url in (
                        ("us", self.us_audio_urls[index]),
                        ("gb", self.gb_audio_urls[index]),
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
        await self.db.upsert_user(
            telegram_user_id=self.telegram_user_id,
            chat_id=self.telegram_user_id,
            username="integration",
            first_name="Integration",
        )
        await self.db.toggle_level(self.telegram_user_id, "c1")
        await self.db.set_pronunciation(self.telegram_user_id, "us")

    async def asyncTearDown(self) -> None:
        await self.db.close()
        with sync_connection(self.db_url) as connection:
            raw = connection.connection.driver_connection
            assert raw is not None
            with raw.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM bot_users WHERE telegram_user_id = %s",
                    (self.telegram_user_id,),
                )
                if self.scheduler_slots:
                    cursor.execute(
                        """
                        DELETE FROM bot_scheduler_runs
                        WHERE scheduled_slot = ANY(%s)
                        """,
                        (self.scheduler_slots,),
                    )
                cursor.execute(
                    "DELETE FROM oald_entries WHERE id = ANY(%s)",
                    (self.entry_ids,),
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
                    (self.audio_urls,),
                )

    async def test_cards_never_repeat_and_slot_is_idempotent(self) -> None:
        first_slot = datetime.now(UTC)
        first = await self.db.reserve_card(
            self.telegram_user_id,
            first_slot,
        )
        same_slot = await self.db.reserve_card(
            self.telegram_user_id,
            first_slot,
        )
        second = await self.db.reserve_card(
            self.telegram_user_id,
            first_slot + timedelta(hours=1),
        )
        exhausted = await self.db.reserve_card(
            self.telegram_user_id,
            first_slot + timedelta(hours=2),
        )

        self.assertIsNotNone(first)
        self.assertIsNone(same_slot)
        self.assertIsNotNone(second)
        self.assertNotEqual(first.entry_id, second.entry_id)
        self.assertIsNone(exhausted)

    async def test_scheduler_slot_can_only_be_claimed_once(self) -> None:
        slot = datetime(2099, 1, 1, tzinfo=UTC) + timedelta(
            seconds=int(self.suffix[:6], 16)
        )
        self.scheduler_slots.append(slot)
        self.assertTrue(await self.db.claim_scheduler_run(slot))
        self.assertFalse(await self.db.claim_scheduler_run(slot))
        await self.db.finish_scheduler_run(
            slot,
            attempted=1,
            delivered=1,
            failed=0,
            skipped=0,
        )

    async def test_both_dialects_return_two_prepared_voice_files(self) -> None:
        await self.db.set_pronunciation(self.telegram_user_id, "both")
        card = await self.db.reserve_card(
            self.telegram_user_id,
            datetime.now(UTC),
        )

        self.assertIsNotNone(card)
        self.assertEqual(card.dialect, "BOTH")
        self.assertEqual(card.ipa_us, "/us/")
        self.assertEqual(card.ipa_gb, "/gb/")
        self.assertIn(card.source_url, self.us_audio_urls)
        self.assertIsNotNone(card.secondary_audio)
        self.assertIn(card.secondary_audio.source_url, self.gb_audio_urls)

    async def test_pronunciation_change_preserves_pause(self) -> None:
        await self.db.set_active(self.telegram_user_id, False)
        user = await self.db.set_pronunciation(self.telegram_user_id, "gb")
        self.assertFalse(user.is_active)
        self.assertEqual(user.pronunciation, "gb")

    async def test_failed_card_does_not_consume_word_or_slot(self) -> None:
        slot = datetime.now(UTC)
        first = await self.db.reserve_card(self.telegram_user_id, slot)
        second = await self.db.reserve_card(
            self.telegram_user_id,
            slot + timedelta(hours=1),
        )
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        await self.db.finish_delivery(
            first.history_id,
            delivered=False,
            error_type="technical_error",
            error_message="boom",
        )
        await self.db.finish_delivery(
            second.history_id,
            delivered=True,
            telegram_message_id=1,
        )
        retry = await self.db.reserve_card(self.telegram_user_id, slot)
        self.assertIsNotNone(retry)
        self.assertEqual(retry.entry_id, first.entry_id)

    async def test_paused_user_can_reserve_one_off_card(self) -> None:
        await self.db.set_active(self.telegram_user_id, False)
        denied = await self.db.reserve_card(
            self.telegram_user_id,
            datetime.now(UTC),
        )
        allowed = await self.db.reserve_card(
            self.telegram_user_id,
            datetime.now(UTC),
            require_active=False,
        )
        self.assertIsNone(denied)
        self.assertIsNotNone(allowed)

    async def test_scheduler_reclaims_failed_run_within_grace(self) -> None:
        slot = datetime.now(UTC) - timedelta(minutes=10)
        self.scheduler_slots.append(slot)
        self.assertTrue(await self.db.claim_scheduler_run(slot, grace_minutes=60))
        await self.db.finish_scheduler_run(
            slot,
            attempted=1,
            delivered=0,
            failed=1,
            skipped=0,
        )
        self.assertFalse(
            await self.db.claim_scheduler_run(slot, grace_minutes=60)
        )
        with sync_connection(self.db_url) as connection:
            raw = connection.connection.driver_connection
            assert raw is not None
            with raw.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE bot_scheduler_runs
                    SET completed_at = CURRENT_TIMESTAMP - INTERVAL '3 minutes'
                    WHERE scheduled_slot = %s
                    """,
                    (slot,),
                )
        self.assertTrue(await self.db.claim_scheduler_run(slot, grace_minutes=60))
        await self.db.finish_scheduler_run(
            slot,
            attempted=1,
            delivered=1,
            failed=0,
            skipped=0,
        )
        with sync_connection(self.db_url) as connection:
            raw = connection.connection.driver_connection
            assert raw is not None
            with raw.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE bot_scheduler_runs
                    SET completed_at = CURRENT_TIMESTAMP - INTERVAL '3 minutes'
                    WHERE scheduled_slot = %s
                    """,
                    (slot,),
                )
        self.assertFalse(
            await self.db.claim_scheduler_run(slot, grace_minutes=60)
        )

    async def test_block_keeps_paused_state(self) -> None:
        await self.db.set_active(self.telegram_user_id, False)
        await self.db.deactivate_user(self.telegram_user_id)
        user = await self.db.upsert_user(
            telegram_user_id=self.telegram_user_id,
            chat_id=self.telegram_user_id,
            username="integration",
            first_name="Integration",
        )
        self.assertFalse(user.is_active)


if __name__ == "__main__":
    unittest.main()
