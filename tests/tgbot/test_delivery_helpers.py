"""Pure delivery helpers."""

from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError

from tests.tgbot.factories import make_card
from tgbot.db.models import Dialect
from tgbot.delivery.card_template import CardTemplateError
from tgbot.delivery.service import (
    card_template_values,
    classify_delivery_error,
    voice_caption,
)
from tgbot.delivery.types import (
    ERROR_TYPE_AUDIO_UNAVAILABLE,
    ERROR_TYPE_BOT_BLOCKED,
    ERROR_TYPE_TECHNICAL,
    ERROR_TYPE_TELEGRAM_ERROR,
    ERROR_TYPE_TELEGRAM_TIMEOUT,
    ERROR_TYPE_TEMPLATE_ERROR,
)


def test_card_template_values_uppercases_words_and_cefr() -> None:
    values = card_template_values(make_card(word_us="color", word_gb="colour"))
    assert values["word"] == "COLOR"
    assert values["word_us"] == "COLOR"
    assert values["word_gb"] == "COLOUR"
    assert values["cefr"] == "B1"
    assert values["ipa"] == "/us/"
    assert "flag_us" in values and "flag_gb" in values


def test_voice_caption_includes_escaped_ipa() -> None:
    assert voice_caption(Dialect.US, "") == "🇺🇸 US"
    assert "<code>/a&amp;b/</code>" in voice_caption(Dialect.GB, "/a&b/")


def test_classify_delivery_error_categories() -> None:
    assert (
        classify_delivery_error(TelegramForbiddenError(method="m", message="x"))
        == ERROR_TYPE_BOT_BLOCKED
    )
    assert (
        classify_delivery_error(CardTemplateError("bad")) == ERROR_TYPE_TEMPLATE_ERROR
    )
    assert (
        classify_delivery_error(TimeoutError("telegram timeout"))
        == ERROR_TYPE_TELEGRAM_TIMEOUT
    )
    assert (
        classify_delivery_error(RuntimeError("voice upload failed"))
        == ERROR_TYPE_AUDIO_UNAVAILABLE
    )
    assert (
        classify_delivery_error(TelegramBadRequest(method="m", message="x"))
        == ERROR_TYPE_TELEGRAM_ERROR
    )
    assert classify_delivery_error(RuntimeError("boom")) == ERROR_TYPE_TECHNICAL
