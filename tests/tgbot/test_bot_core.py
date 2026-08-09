import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, datetime, time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

from tgbot.bot_config import BotConfig
from tgbot.db import AdminUserDetail, AdminWordMatch, ReservedAudio, ReservedCard
from tgbot.delivery import (
    CardDeliveryService,
    CardTemplate,
    CardTemplateError,
    classify_delivery_error,
)
from tgbot.delivery.scheduler import due_schedule_slots
from tgbot.handlers.admin import _delivery_state
from tgbot.handlers.admin_keyboards import (
    admin_main_keyboard,
    word_categories_keyboard,
)
from tgbot.secrets import Secrets

VALID_TEMPLATE = """<b>{word}</b> {lexical_category} {cefr}
{definition} {ipa} {example} {translation} {dialect}"""


class BotConfigTests(unittest.TestCase):
    def test_environment_configuration_is_parsed(self) -> None:
        test_secrets = Secrets.load(
            {
                "TELEGRAM_BOT_TOKEN": "token",
                "TELEGRAM_ADMIN_IDS": "123, 456",
                "OALD_DATABASE_URL": "postgresql+psycopg://localhost/test",
            }
        )
        with patch("tgbot.bot_config.secrets", test_secrets):
            config = BotConfig.load()

        self.assertEqual(config.admin_ids, frozenset({123, 456}))
        self.assertEqual(config.schedule.send_times, (time(13, 0), time(20, 0)))
        self.assertEqual(
            config.schedule.text, "13:00, 20:00 (Europe/Moscow)"
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
            _delivery_state(make_admin_user_detail(is_active=True)),
            "включена",
        )
        self.assertEqual(
            _delivery_state(
                make_admin_user_detail(
                    is_active=False,
                    paused_at=datetime.now(UTC),
                )
            ),
            "приостановлена",
        )
        self.assertEqual(
            _delivery_state(
                make_admin_user_detail(
                    is_active=False,
                    blocked_at=datetime.now(UTC),
                )
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
                    make_word_match(10, lexical_category="noun", cefr="a1"),
                    make_word_match(11, lexical_category="verb", cefr="b1"),
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
            },
        )

    def test_word_categories_keyboard_uses_entry_ids(self) -> None:
        keyboard = word_categories_keyboard(
            (
                make_word_match(10, lexical_category="noun", cefr="a1"),
                make_word_match(11, lexical_category="verb", cefr="b1"),
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


class VoiceDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_voice_is_uploaded_and_telegram_file_id_is_cached(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            template_path = Path(temporary_directory) / "card.html"
            template_path.write_text(VALID_TEMPLATE, encoding="utf-8")
            db = SimpleNamespace(
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
            service = CardDeliveryService(db, CardTemplate(template_path))
            card = make_reserved_card("audio/ogg", "test.voice.ogg")

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
            db.cache_audio_file_id.assert_awaited_once_with(
                card.source_url,
                "voice",
                "telegram-voice-id",
            )

    async def test_partial_send_counts_as_delivered(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            template_path = Path(temporary_directory) / "card.html"
            template_path.write_text(VALID_TEMPLATE, encoding="utf-8")
            card = make_reserved_card("audio/ogg", "test.voice.ogg")
            db = SimpleNamespace(
                reserve_card=AsyncMock(return_value=card),
                finish_delivery=AsyncMock(),
                deactivate_user=AsyncMock(),
                cached_audio_file_id=AsyncMock(return_value=None),
                cache_audio_file_id=AsyncMock(),
                clear_cached_audio_file_id=AsyncMock(),
            )
            bot = SimpleNamespace(
                send_message=AsyncMock(),
                send_voice=AsyncMock(side_effect=RuntimeError("voice failed")),
            )
            service = CardDeliveryService(db, CardTemplate(template_path))

            outcome = await service.deliver(
                bot,
                telegram_user_id=1,
                chat_id=1,
                scheduled_slot=datetime.now(UTC),
            )

            self.assertEqual(outcome.status, "delivered")
            db.finish_delivery.assert_awaited_once_with(
                card.history_id,
                delivered=True,
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
            db = SimpleNamespace(
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
                db,
                CardTemplate(template_path),
                CardTemplate(both_template_path),
            )
            card = replace(
                make_reserved_card("audio/ogg", "test-us.voice.ogg"),
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
            self.assertEqual(db.cache_audio_file_id.await_count, 2)


def make_admin_user_detail(**overrides: object) -> AdminUserDetail:
    now = datetime.now(UTC)
    user = AdminUserDetail(
        telegram_user_id=1,
        chat_id=1,
        username="",
        first_name="",
        selected_levels=(),
        pronunciation=None,
        onboarding_completed=True,
        is_active=True,
        created_at=now,
        updated_at=now,
        last_delivery_at=None,
        paused_at=None,
        blocked_at=None,
        delivered_cards=0,
        last_successful_delivery=None,
    )
    return replace(user, **overrides)  # type: ignore[arg-type]


def make_word_match(
    entry_id: int,
    lexical_category: str,
    cefr: str,
) -> AdminWordMatch:
    return AdminWordMatch(
        id=entry_id,
        word_us="word",
        word_gb="word",
        lexical_category=lexical_category,
        cefr=cefr,
    )


def make_reserved_card(
    content_type: str = "audio/ogg",
    filename: str = "test.voice.ogg",
) -> ReservedCard:
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


if __name__ == "__main__":
    unittest.main()
