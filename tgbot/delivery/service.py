"""Reserve and deliver vocabulary cards with Telegram audio-file caching."""

from __future__ import annotations

import asyncio
import html
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import TypeVar

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import BufferedInputFile, Message
from pydantic import BaseModel, ConfigDict

from tgbot.db import Database
from tgbot.db.models import (
    Card,
    Dialect,
    DialectPreference,
    DialectVariant,
    TelegramSendMethod,
)
from tgbot.delivery.card_template import CardTemplate, CardTemplateError
from tgbot.delivery.types import (
    BOTH_CARD_TEMPLATE_PATH,
    CARD_TEMPLATE_PATH,
    ERROR_TYPE_AUDIO_UNAVAILABLE,
    ERROR_TYPE_BOT_BLOCKED,
    ERROR_TYPE_TECHNICAL,
    ERROR_TYPE_TELEGRAM_ERROR,
    ERROR_TYPE_TELEGRAM_TIMEOUT,
    ERROR_TYPE_TEMPLATE_ERROR,
    SEND_KIND_TEXT,
    DeliveryStatus,
)
from tgbot.localization import locale

LOGGER = logging.getLogger("tgbot.delivery")

T = TypeVar("T")

PREVIEW_PREFERENCES = (
    DialectPreference.GB,
    DialectPreference.US,
    DialectPreference.BOTH,
)


class DeliveryOutcome(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: DeliveryStatus
    card: Card | None = None


class CardDeliveryService:
    def __init__(self, db: Database):
        self.db = db
        self.template = CardTemplate(CARD_TEMPLATE_PATH)
        self.both_template = CardTemplate(BOTH_CARD_TEMPLATE_PATH)

    async def deliver(
        self,
        bot: Bot,
        telegram_user_id: int,
        scheduled_slot: datetime | None = None,
    ) -> DeliveryOutcome:
        card = await self.db.reserve_card(telegram_user_id, scheduled_slot)
        if card is None:
            return DeliveryOutcome(status=DeliveryStatus.SKIPPED)

        text_sent = False
        try:
            await self.send_card(
                bot,
                telegram_user_id=telegram_user_id,
                card=card,
            )
            text_sent = True
            return DeliveryOutcome(status=DeliveryStatus.DELIVERED, card=card)

        except TelegramForbiddenError as exc:
            await self.finish_after_error(card, text_sent=text_sent, exc=exc)
            await self.db.deactivate_user(telegram_user_id)
            LOGGER.info("Deactivated unreachable Telegram user %s", telegram_user_id)
            return DeliveryOutcome(
                status=(
                    DeliveryStatus.DELIVERED if text_sent else DeliveryStatus.FAILED
                ),
                card=card,
            )

        except Exception as exc:  # noqa: BLE001
            await self.finish_after_error(card, text_sent=text_sent, exc=exc)
            if text_sent:
                LOGGER.exception(
                    "Card voice delivery failed after text for user %s; "
                    "counting as delivered",
                    telegram_user_id,
                )
                return DeliveryOutcome(status=DeliveryStatus.DELIVERED, card=card)

            LOGGER.exception("Card delivery failed for user %s", telegram_user_id)
            return DeliveryOutcome(status=DeliveryStatus.FAILED, card=card)

    async def send_preview(self, bot: Bot, telegram_user_id: int, card: Card) -> None:
        """Send GB, US, and both variants for admin visual QA."""
        for preference in PREVIEW_PREFERENCES:
            await self.send_card(
                bot,
                telegram_user_id=telegram_user_id,
                card=card.for_preference(preference),
            )

    async def send_card(
        self,
        bot: Bot,
        telegram_user_id: int,
        card: Card,
    ) -> None:
        await self.send_card_text(
            bot,
            telegram_user_id=telegram_user_id,
            text=self.render_card(card),
        )
        message = await self.send_card_voices(
            bot,
            telegram_user_id=telegram_user_id,
            card=card,
        )
        await self.finish_ok(card, message.message_id)

    def render_card(self, card: Card) -> str:
        template = self.both_template if card.is_both else self.template
        return template.render(card_template_values(card))

    async def send_card_text(
        self,
        bot: Bot,
        telegram_user_id: int,
        text: str,
    ) -> None:
        await call_with_retry_after(
            lambda: bot.send_message(chat_id=telegram_user_id, text=text),
            kind=SEND_KIND_TEXT,
        )

    async def send_card_voices(
        self,
        bot: Bot,
        telegram_user_id: int,
        card: Card,
    ) -> Message:
        message: Message | None = None
        for variant in card.variants():
            message = await self.send_voice_attachment(
                bot,
                telegram_user_id=telegram_user_id,
                variant=variant,
            )
        if message is None:
            raise RuntimeError("card has no dialect variants to send")
        return message

    async def send_voice_attachment(
        self,
        bot: Bot,
        telegram_user_id: int,
        variant: DialectVariant,
    ) -> Message:
        audio = variant.audio
        filename = audio.filename or f"{variant.word}.voice.ogg"
        caption = voice_caption(variant.dialect, variant.ipa)

        async def send(file_reference: str | BufferedInputFile) -> Message:
            return await call_with_retry_after(
                lambda: bot.send_voice(
                    chat_id=telegram_user_id,
                    voice=file_reference,
                    caption=caption,
                ),
                kind=TelegramSendMethod.VOICE,
            )

        cached_file_id = await self.db.get_cached_audio_file_id(audio.source_url)
        if cached_file_id:
            try:
                return await send(cached_file_id)
            except TelegramBadRequest:
                LOGGER.warning(
                    "Telegram rejected cached file_id for %s; uploading bytes again",
                    audio.source_url,
                )
                await self.db.clear_cached_audio_file_id(audio.source_url)

        message = await send(BufferedInputFile(audio.audio_data, filename=filename))
        if message.voice:
            await self.db.set_cached_audio_file_id(
                audio.source_url,
                message.voice.file_id,
            )
        return message

    async def finish_ok(self, card: Card, telegram_message_id: int) -> None:
        await self.db.finish_delivery(
            card.user_card_id,
            delivered=True,
            telegram_message_id=telegram_message_id,
        )

    async def finish_after_error(
        self,
        card: Card,
        text_sent: bool,
        exc: Exception,
    ) -> None:
        if text_sent:
            await self.db.finish_delivery(card.user_card_id, delivered=True)
            return
        await self.db.finish_delivery(
            card.user_card_id,
            delivered=False,
            error_type=classify_delivery_error(exc),
            error_message=str(exc),
        )


def card_template_values(card: Card) -> dict[str, str]:
    """Build template placeholders (same groups as card_template field sets)."""
    primary = card.primary
    labels = locale.labels
    words = {
        "word": primary.word.upper(),
        "word_us": card.word_us.upper(),
        "word_gb": card.word_gb.upper(),
    }
    ipa = {
        "ipa": primary.ipa,
        "ipa_us": (card.us or primary).ipa,
        "ipa_gb": (card.gb or primary).ipa,
    }
    required = {
        "lexical_category": card.lexical_category,
        "cefr": str(card.cefr).upper(),
        "definition": card.definition,
        "example": card.example,
        "translation": card.translation,
    }
    display = {
        "dialect": str(primary.dialect),
        "dialect_flag": locale.dialect_flag(primary.dialect),
        "heading_definition": labels.card_heading_definition,
        "heading_example": labels.card_heading_example,
        "heading_translation": labels.card_heading_translation,
        "flag_us": locale.dialect_flag(Dialect.US),
        "flag_gb": locale.dialect_flag(Dialect.GB),
    }
    return words | ipa | required | display


def voice_caption(dialect: Dialect, ipa: str) -> str:
    label = locale.dialect_caption(dialect)
    transcription = ipa.strip()
    if not transcription:
        return label
    return f"{label} · <code>{html.escape(transcription)}</code>"


def classify_delivery_error(exc: Exception) -> str:
    """Return a stable, queryable category for a delivery exception."""
    if isinstance(exc, TelegramForbiddenError):
        return ERROR_TYPE_BOT_BLOCKED
    if isinstance(exc, CardTemplateError):
        return ERROR_TYPE_TEMPLATE_ERROR

    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if "timeout" in name or "timeout" in message:
        return ERROR_TYPE_TELEGRAM_TIMEOUT
    if "audio" in message or "voice" in message:
        return ERROR_TYPE_AUDIO_UNAVAILABLE
    if name.startswith("telegram"):
        return ERROR_TYPE_TELEGRAM_ERROR
    return ERROR_TYPE_TECHNICAL


async def call_with_retry_after(
    operation: Callable[[], Awaitable[T]],
    kind: str,
) -> T:
    try:
        return await operation()
    except TelegramRetryAfter as exc:
        LOGGER.warning(
            "Telegram %s rate limit; retrying in %s seconds",
            kind,
            exc.retry_after,
        )
        await asyncio.sleep(float(exc.retry_after))
        return await operation()
