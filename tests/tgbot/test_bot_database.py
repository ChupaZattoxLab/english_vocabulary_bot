import unittest
import uuid
from datetime import UTC, datetime, timedelta

from psycopg.types.json import Jsonb

from tests.support import TEST_OALD_DATABASE_URL, requires_oald_database
from tgbot.db import Database


@requires_oald_database
class BotDatabaseIntegrationTests(unittest.IsolatedAsyncioTestCase):
    database_url = TEST_OALD_DATABASE_URL

    async def asyncSetUp(self) -> None:
        import psycopg

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
        self.database = Database(self.database_url, pool_size=2)
        await self.database.open()
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for index in range(2):
                    cursor.execute(
                        """
                        INSERT INTO oald_entries (
                            word_us, word_gb, lexical_category, cefr,
                            definition_url_oxford, definition_url_cambridge,
                            ipa_us, ipa_gb, definition, example,
                            audio_source_us, audio_source_gb, translations
                        ) VALUES (
                            %s, %s, 'noun', 'c2', %s, '',
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
        await self.database.upsert_user(
            telegram_user_id=self.telegram_user_id,
            chat_id=self.telegram_user_id,
            username="integration",
            first_name="Integration",
        )
        await self.database.toggle_level(self.telegram_user_id, "c2")
        await self.database.set_pronunciation(self.telegram_user_id, "us")

    async def asyncTearDown(self) -> None:
        import psycopg

        await self.database.close()
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
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
        first = await self.database.reserve_card(
            self.telegram_user_id,
            first_slot,
        )
        same_slot = await self.database.reserve_card(
            self.telegram_user_id,
            first_slot,
        )
        second = await self.database.reserve_card(
            self.telegram_user_id,
            first_slot + timedelta(hours=1),
        )
        exhausted = await self.database.reserve_card(
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
        self.assertTrue(await self.database.claim_scheduler_run(slot))
        self.assertFalse(await self.database.claim_scheduler_run(slot))
        await self.database.finish_scheduler_run(
            slot,
            attempted=1,
            delivered=1,
            failed=0,
            skipped=0,
        )

    async def test_both_dialects_return_two_prepared_voice_files(self) -> None:
        await self.database.set_pronunciation(self.telegram_user_id, "both")
        card = await self.database.reserve_card(
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
        await self.database.set_active(self.telegram_user_id, False)
        user = await self.database.set_pronunciation(self.telegram_user_id, "gb")
        self.assertFalse(user.is_active)
        self.assertEqual(user.pronunciation, "gb")

    async def test_failed_card_does_not_consume_word_or_slot(self) -> None:
        slot = datetime.now(UTC)
        first = await self.database.reserve_card(self.telegram_user_id, slot)
        second = await self.database.reserve_card(
            self.telegram_user_id,
            slot + timedelta(hours=1),
        )
        self.assertIsNotNone(first)
        self.assertIsNotNone(second)
        await self.database.finish_delivery(
            first.history_id,
            delivered=False,
            error_type="technical_error",
            error_message="boom",
        )
        await self.database.finish_delivery(
            second.history_id,
            delivered=True,
            telegram_message_id=1,
        )
        retry = await self.database.reserve_card(self.telegram_user_id, slot)
        self.assertIsNotNone(retry)
        self.assertEqual(retry.entry_id, first.entry_id)

    async def test_paused_user_can_reserve_one_off_card(self) -> None:
        await self.database.set_active(self.telegram_user_id, False)
        denied = await self.database.reserve_card(
            self.telegram_user_id,
            datetime.now(UTC),
        )
        allowed = await self.database.reserve_card(
            self.telegram_user_id,
            datetime.now(UTC),
            require_active=False,
        )
        self.assertIsNone(denied)
        self.assertIsNotNone(allowed)

    async def test_scheduler_reclaims_failed_run_within_grace(self) -> None:
        import psycopg

        slot = datetime.now(UTC) - timedelta(minutes=10)
        self.scheduler_slots.append(slot)
        self.assertTrue(await self.database.claim_scheduler_run(slot, grace_minutes=60))
        await self.database.finish_scheduler_run(
            slot,
            attempted=1,
            delivered=0,
            failed=1,
            skipped=0,
        )
        self.assertFalse(
            await self.database.claim_scheduler_run(slot, grace_minutes=60)
        )
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE bot_scheduler_runs
                    SET completed_at = CURRENT_TIMESTAMP - INTERVAL '3 minutes'
                    WHERE scheduled_slot = %s
                    """,
                    (slot,),
                )
        self.assertTrue(await self.database.claim_scheduler_run(slot, grace_minutes=60))
        await self.database.finish_scheduler_run(
            slot,
            attempted=1,
            delivered=1,
            failed=0,
            skipped=0,
        )
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE bot_scheduler_runs
                    SET completed_at = CURRENT_TIMESTAMP - INTERVAL '3 minutes'
                    WHERE scheduled_slot = %s
                    """,
                    (slot,),
                )
        self.assertFalse(
            await self.database.claim_scheduler_run(slot, grace_minutes=60)
        )

    async def test_block_keeps_paused_state(self) -> None:
        await self.database.set_active(self.telegram_user_id, False)
        await self.database.deactivate_user(self.telegram_user_id)
        user = await self.database.upsert_user(
            telegram_user_id=self.telegram_user_id,
            chat_id=self.telegram_user_id,
            username="integration",
            first_name="Integration",
        )
        self.assertFalse(user.is_active)


if __name__ == "__main__":
    unittest.main()
