import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from tgbot.config import BotConfig, ConfigError
from tgbot.db import ReservedAudio, ReservedCard
from tgbot.delivery import (
    CardDeliveryService,
    CardTemplate,
    CardTemplateError,
    classify_delivery_error,
    send_method,
)
from tgbot.delivery.scheduler import due_schedule_slots
from tgbot.handlers.admin import _delivery_state
from tgbot.handlers.admin_keyboards import (
    admin_main_keyboard,
    word_categories_keyboard,
)

VALID_TEMPLATE = """<b>{word}</b> {lexical_category} {cefr}
{definition} {ipa} {example} {translation} {dialect}"""


class BotConfigTests(unittest.TestCase):
    def test_environment_configuration_is_parsed(self) -> None:
        config = BotConfig.from_env(
            {
                "TELEGRAM_BOT_TOKEN": "token",
                "TELEGRAM_ADMIN_IDS": "123, 456",
                "OALD_DATABASE_URL": "postgresql://localhost/test",
                "BOT_TIMEZONE": "Europe/Amsterdam",
                "BOT_SEND_TIMES": "20:00,09:00,14:00",
            }
        )

        self.assertEqual(config.admin_ids, frozenset({123, 456}))
        self.assertEqual(
            config.send_times,
            (time(9, 0), time(14, 0), time(20, 0)),
        )
        self.assertEqual(config.schedule_text, "09:00, 14:00, 20:00 (Europe/Amsterdam)")
        self.assertEqual(
            config.both_card_template_path.name,
            "card_template_both.html",
        )

    def test_exactly_three_unique_times_are_required(self) -> None:
        with self.assertRaises(ConfigError):
            BotConfig.from_env(
                {
                    "TELEGRAM_BOT_TOKEN": "token",
                    "OALD_DATABASE_URL": "postgresql://localhost/test",
                    "BOT_SEND_TIMES": "09:00,14:00",
                }
            )


class CardTemplateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.path = Path(self.temporary_directory.name) / "card.html"

    def test_values_are_html_escaped_but_template_markup_is_preserved(self) -> None:
        self.path.write_text(VALID_TEMPLATE, encoding="utf-8")
        template = CardTemplate(self.path)

        rendered = template.render(
            {
                "word": "a < b",
                "lexical_category": "noun",
                "cefr": "A1",
                "definition": "x & y",
                "ipa": "/test/",
                "example": "example",
                "translation": "перевод",
                "dialect": "US",
            }
        )

        self.assertIn("<b>a &lt; b</b>", rendered)
        self.assertIn("x &amp; y", rendered)

    def test_required_fields_cannot_be_removed(self) -> None:
        self.path.write_text("{word}", encoding="utf-8")
        with self.assertRaises(CardTemplateError):
            CardTemplate(self.path)

    def test_word_upper_can_replace_word(self) -> None:
        self.path.write_text(
            "{dialect_flag} <b>{word_upper}</b> {lexical_category} {cefr} "
            "{definition} {ipa} {example} {translation}",
            encoding="utf-8",
        )
        template = CardTemplate(self.path)
        rendered = template.render(
            {
                "dialect_flag": "🇺🇸",
                "word_upper": "APPLE",
                "lexical_category": "noun",
                "cefr": "A1",
                "definition": "fruit",
                "ipa": "/ˈæpəl/",
                "example": "an apple",
                "translation": "яблоко",
            }
        )
        self.assertIn("🇺🇸 <b>APPLE</b>", rendered)

    def test_both_template_accepts_both_ipa_fields(self) -> None:
        self.path.write_text(
            "{word_us_upper} {word_gb_upper} {lexical_category} {cefr} "
            "{definition} {ipa_us} {ipa_gb} {example} {translation}",
            encoding="utf-8",
        )
        CardTemplate(self.path)

    def test_explicit_reload_validates_changed_template(self) -> None:
        self.path.write_text(VALID_TEMPLATE, encoding="utf-8")
        template = CardTemplate(self.path)
        self.path.write_text("{word}", encoding="utf-8")

        with self.assertRaises(CardTemplateError):
            template.reload()


class AdminHelperTests(unittest.TestCase):
    def test_user_delivery_states_are_distinct(self) -> None:
        self.assertEqual(
            _delivery_state({"is_active": True, "paused_at": None, "blocked_at": None}),
            "включена",
        )
        self.assertEqual(
            _delivery_state(
                {"is_active": False, "paused_at": object(), "blocked_at": None}
            ),
            "приостановлена",
        )
        self.assertEqual(
            _delivery_state(
                {"is_active": False, "paused_at": None, "blocked_at": object()}
            ),
            "бот заблокирован",
        )

    def test_delivery_errors_have_stable_categories(self) -> None:
        self.assertEqual(
            classify_delivery_error(TimeoutError("timeout")), "telegram_timeout"
        )
        self.assertEqual(
            classify_delivery_error(CardTemplateError("bad template")),
            "template_error",
        )

    def test_admin_keyboards_use_short_namespaced_callbacks(self) -> None:
        keyboards = (
            admin_main_keyboard(),
            word_categories_keyboard(
                (
                    {"id": 10, "lexical_category": "noun", "cefr": "a1"},
                    {"id": 11, "lexical_category": "verb", "cefr": "b1"},
                )
            ),
        )
        callback_values = [
            button.callback_data
            for keyboard in keyboards
            for row in keyboard.inline_keyboard
            for button in row
        ]

        self.assertTrue(callback_values)
        self.assertTrue(all(value.startswith("admin:") for value in callback_values))
        self.assertTrue(
            all(len(value.encode("utf-8")) <= 64 for value in callback_values)
        )

    def test_main_admin_keyboard_has_expected_sections(self) -> None:
        values = {
            button.callback_data
            for row in admin_main_keyboard().inline_keyboard
            for button in row
        }
        self.assertEqual(
            values,
            {
                "admin:overview",
                "admin:users",
                "admin:test_card",
            },
        )

    def test_word_categories_keyboard_uses_entry_ids(self) -> None:
        keyboard = word_categories_keyboard(
            (
                {"id": 10, "lexical_category": "noun", "cefr": "a1"},
                {"id": 11, "lexical_category": "verb", "cefr": "b1"},
            )
        )
        buttons = [button for row in keyboard.inline_keyboard for button in row]
        self.assertEqual([button.text for button in buttons], ["noun", "verb"])
        self.assertEqual(
            [button.callback_data for button in buttons],
            ["admin:word:10", "admin:word:11"],
        )


class SchedulerTests(unittest.TestCase):
    def test_due_slot_uses_configured_timezone(self) -> None:
        slots = due_schedule_slots(
            datetime(2026, 8, 1, 7, 30, tzinfo=UTC),
            timezone_value=ZoneInfo("Europe/Amsterdam"),
            send_times=(time(9), time(14), time(20)),
            grace_minutes=60,
        )

        self.assertEqual(
            slots,
            (datetime(2026, 8, 1, 7, 0, tzinfo=UTC),),
        )

    def test_old_slots_are_not_sent_late(self) -> None:
        slots = due_schedule_slots(
            datetime(2026, 8, 1, 10, 30, tzinfo=UTC),
            timezone_value=ZoneInfo("Europe/Amsterdam"),
            send_times=(time(9), time(14), time(20)),
            grace_minutes=60,
        )
        self.assertEqual(slots, ())


class DeliveryFormatTests(unittest.TestCase):
    def card(self, content_type: str, filename: str) -> ReservedCard:
        return ReservedCard(
            history_id=1,
            entry_id=1,
            word="test",
            lexical_category="noun",
            cefr="A1",
            definition="definition",
            example="example",
            ipa="/test/",
            dialect="US",
            translation="тест",
            source_url="https://example.test/audio",
            audio_data=b"audio",
            content_type=content_type,
            filename=filename,
        )

    def test_prepared_audio_is_sent_as_voice(self) -> None:
        self.assertEqual(send_method(self.card("audio/ogg", "test.voice.ogg")), "voice")


class VoiceDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_voice_is_uploaded_and_telegram_file_id_is_cached(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            template_path = Path(temporary_directory) / "card.html"
            template_path.write_text(VALID_TEMPLATE, encoding="utf-8")
            database = SimpleNamespace(
                cached_audio_file_id=AsyncMock(return_value=None),
                cache_audio_file_id=AsyncMock(),
                clear_cached_audio_file_id=AsyncMock(),
            )
            bot = SimpleNamespace(
                send_voice=AsyncMock(
                    return_value=SimpleNamespace(
                        message_id=10,
                        voice=SimpleNamespace(file_id="telegram-voice-id"),
                    )
                ),
                send_message=AsyncMock(),
            )
            service = CardDeliveryService(database, CardTemplate(template_path))
            card = DeliveryFormatTests().card("audio/ogg", "test.voice.ogg")

            await service._send_reserved(bot, chat_id=123, card=card)

            bot.send_voice.assert_awaited_once()
            bot.send_message.assert_awaited_once()
            self.assertIn(
                "test",
                bot.send_message.await_args.kwargs["text"],
            )
            self.assertEqual(
                bot.send_voice.await_args.kwargs["voice"].filename,
                "test.voice.ogg",
            )
            self.assertEqual(
                bot.send_voice.await_args.kwargs["caption"],
                "🇺🇸 US · <code>/test/</code>",
            )
            database.cache_audio_file_id.assert_awaited_once_with(
                card.source_url,
                "voice",
                "telegram-voice-id",
            )

    async def test_both_dialects_use_both_template_and_send_two_voices(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            template_path = Path(temporary_directory) / "card.html"
            both_template_path = Path(temporary_directory) / "card_both.html"
            template_path.write_text(VALID_TEMPLATE, encoding="utf-8")
            both_template_path.write_text(
                "{word_us_upper} {word_gb_upper} {lexical_category} {cefr} "
                "{definition} {ipa_us} {ipa_gb} {example} {translation}",
                encoding="utf-8",
            )
            database = SimpleNamespace(
                cached_audio_file_id=AsyncMock(return_value=None),
                cache_audio_file_id=AsyncMock(),
                clear_cached_audio_file_id=AsyncMock(),
            )
            bot = SimpleNamespace(
                send_voice=AsyncMock(
                    side_effect=[
                        SimpleNamespace(
                            message_id=10,
                            voice=SimpleNamespace(file_id="us-file-id"),
                        ),
                        SimpleNamespace(
                            message_id=11,
                            voice=SimpleNamespace(file_id="gb-file-id"),
                        ),
                    ]
                ),
                send_message=AsyncMock(),
            )
            service = CardDeliveryService(
                database,
                CardTemplate(template_path),
                CardTemplate(both_template_path),
            )
            card = replace(
                DeliveryFormatTests().card("audio/ogg", "test-us.voice.ogg"),
                dialect="BOTH",
                word_us="color",
                word_gb="colour",
                ipa_us="/us/",
                ipa_gb="/gb/",
                secondary_audio=ReservedAudio(
                    dialect="GB",
                    source_url="https://example.test/audio-gb",
                    audio_data=b"gb-audio",
                    content_type="audio/ogg",
                    filename="test-gb.voice.ogg",
                ),
            )

            await service._send_reserved(bot, chat_id=123, card=card)

            self.assertEqual(bot.send_voice.await_count, 2)
            bot.send_message.assert_awaited_once()
            card_text = bot.send_message.await_args.kwargs["text"]
            self.assertIn("COLOR", card_text)
            self.assertIn("COLOUR", card_text)
            first_call, second_call = bot.send_voice.await_args_list
            self.assertEqual(
                first_call.kwargs["caption"],
                "🇺🇸 US · <code>/us/</code>",
            )
            self.assertEqual(
                second_call.kwargs["caption"],
                "🇬🇧 GB · <code>/gb/</code>",
            )
            self.assertEqual(database.cache_audio_file_id.await_count, 2)


if __name__ == "__main__":
    unittest.main()
