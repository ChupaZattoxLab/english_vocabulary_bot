"""Reserve and deliver vocabulary cards with Telegram audio-file caching."""

from __future__ import annotations

import asyncio
import html
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, TypeVar

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import BufferedInputFile, Message

from tgbot.constants import (
    DELIVERY_STATUS_DELIVERED,
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_SKIPPED,
    ERROR_TYPE_AUDIO_UNAVAILABLE,
    ERROR_TYPE_BOT_BLOCKED,
    ERROR_TYPE_TECHNICAL,
    ERROR_TYPE_TELEGRAM_ERROR,
    ERROR_TYPE_TELEGRAM_TIMEOUT,
    ERROR_TYPE_TEMPLATE_ERROR,
    SEND_KIND_TEXT,
    SEND_METHOD_VOICE,
)
from tgbot.db import Database
from tgbot.delivery.card_template import (
    BOTH_CARD_TEMPLATE_PATH,
    CARD_TEMPLATE_PATH,
    CardTemplate,
    CardTemplateError,
)
from tgbot.localization import locale
from tgbot.models import Card, Dialect

LOGGER = logging.getLogger("tgbot.delivery")

DeliveryStatus = Literal["delivered", "failed", "skipped"]
T = TypeVar("T")


@dataclass(frozen=True)
class DeliveryOutcome:
    status: DeliveryStatus
    card: Card | None = None


class CardDeliveryService:
    def __init__(
        self,
        db: Database,
        template: CardTemplate | None = None,
        both_template: CardTemplate | None = None,
    ):
        self.db = db
        self.template = template or CardTemplate(CARD_TEMPLATE_PATH)
        self.both_template = both_template or CardTemplate(BOTH_CARD_TEMPLATE_PATH)

    async def deliver(
        self,
        bot: Bot,
        telegram_user_id: int,
        scheduled_slot: datetime | None = None,
    ) -> DeliveryOutcome:
        card = await self.db.reserve_card(
            telegram_user_id,
            scheduled_slot,
        )
        if card is None:
            return DeliveryOutcome(DELIVERY_STATUS_SKIPPED)

        text_sent = False

        try:
            rendered = self.render_card(card)
            await self._send_card_text(
                bot,
                telegram_user_id=telegram_user_id,
                text=rendered,
            )
            text_sent = True

            message = await self._send_card_voices(
                bot,
                telegram_user_id=telegram_user_id,
                card=card,
            )
            await self.db.finish_delivery(
                card.user_card_id,
                delivered=True,
                telegram_message_id=message.message_id,
            )
            return DeliveryOutcome(DELIVERY_STATUS_DELIVERED, card)

        except TelegramForbiddenError as exc:
            if text_sent:
                await self.db.finish_delivery(
                    card.user_card_id,
                    delivered=True,
                )
            else:
                await self.db.finish_delivery(
                    card.user_card_id,
                    delivered=False,
                    error_type=classify_delivery_error(exc),
                    error_message=str(exc),
                )

            await self.db.deactivate_user(telegram_user_id)
            LOGGER.info("Deactivated unreachable Telegram user %s", telegram_user_id)

            return DeliveryOutcome(
                DELIVERY_STATUS_DELIVERED if text_sent else DELIVERY_STATUS_FAILED,
                card,
            )

        except Exception as exc:  # noqa: BLE001
            if text_sent:
                await self.db.finish_delivery(
                    card.user_card_id,
                    delivered=True,
                )
                LOGGER.exception(
                    "Card voice delivery failed after text for user %s; "
                    "counting as delivered",
                    telegram_user_id,
                )
                return DeliveryOutcome(DELIVERY_STATUS_DELIVERED, card)

            await self.db.finish_delivery(
                card.user_card_id,
                delivered=False,
                error_type=classify_delivery_error(exc),
                error_message=str(exc),
            )
            LOGGER.exception("Card delivery failed for user %s", telegram_user_id)
            return DeliveryOutcome(DELIVERY_STATUS_FAILED, card)

    async def send_preview(self, bot: Bot, telegram_user_id: int, card: Card) -> None:
        """Send GB, US, and both variants for admin visual QA."""
        for preference in ("gb", "us", "both"):
            await self._send_card(
                bot,
                telegram_user_id=telegram_user_id,
                card=card.for_preference(preference),
            )

    def render_card(self, card: Card) -> str:
        template = self.both_template if card.is_both else self.template
        primary = card.primary
        return template.render(
            {
                "word": primary.word,
                "word_upper": primary.word.upper(),
                "word_us": (card.us or primary).word,
                "word_us_upper": (card.us or primary).word.upper(),
                "word_gb": (card.gb or primary).word,
                "word_gb_upper": (card.gb or primary).word.upper(),
                "lexical_category": card.lexical_category,
                "cefr": card.cefr,
                "definition": card.definition,
                "ipa": primary.ipa,
                "ipa_us": (card.us or primary).ipa,
                "ipa_gb": (card.gb or primary).ipa,
                "example": card.example,
                "translation": card.translation,
                "dialect": primary.dialect,
                "dialect_flag": locale.dialect_flag(primary.dialect),
                "heading_definition": locale.labels.card_heading_definition,
                "heading_example": locale.labels.card_heading_example,
                "heading_translation": locale.labels.card_heading_translation,
                "flag_us": locale.labels.dialect_flags["US"],
                "flag_gb": locale.labels.dialect_flags["GB"],
            }
        )

    async def _send_card(
        self,
        bot: Bot,
        telegram_user_id: int,
        card: Card,
    ) -> Message:
        rendered = self.render_card(card)

        await self._send_card_text(
            bot,
            telegram_user_id=telegram_user_id,
            text=rendered,
        )

        return await self._send_card_voices(
            bot,
            telegram_user_id=telegram_user_id,
            card=card,
        )

    async def _send_card_voices(
        self,
        bot: Bot,
        telegram_user_id: int,
        card: Card,
    ) -> Message:
        message: Message | None = None
        for variant in card.variants():
            message = await self._send_voice_attachment(
                bot,
                telegram_user_id=telegram_user_id,
                source_url=variant.audio.source_url,
                audio_data=variant.audio.audio_data,
                filename=variant.audio.filename or f"{variant.word}.voice.ogg",
                caption=voice_caption(variant.dialect, variant.ipa),
            )

        if message is None:
            raise RuntimeError("card has no dialect variants to send")

        return message

    async def _send_card_text(
        self,
        bot: Bot,
        telegram_user_id: int,
        text: str,
    ) -> None:
        await _call_with_retry_after(
            lambda: bot.send_message(chat_id=telegram_user_id, text=text),
            kind=SEND_KIND_TEXT,
        )

    async def _send_voice_attachment(
        self,
        bot: Bot,
        telegram_user_id: int,
        source_url: str,
        audio_data: bytes,
        filename: str,
        caption: str | None,
    ) -> Message:
        async def send(file_reference: str | BufferedInputFile) -> Message:
            return await _call_with_retry_after(
                lambda: bot.send_voice(
                    chat_id=telegram_user_id,
                    voice=file_reference,
                    caption=caption,
                ),
                kind=SEND_METHOD_VOICE,
            )

        cached_file_id = await self.db.get_cached_audio_file_id(source_url)

        if cached_file_id:
            try:
                return await send(cached_file_id)
            except TelegramBadRequest:
                LOGGER.warning(
                    "Telegram rejected cached file_id for %s; uploading bytes again",
                    source_url,
                )
                await self.db.clear_cached_audio_file_id(source_url)

        upload = BufferedInputFile(audio_data, filename=filename)
        message = await send(upload)

        if message.voice:
            await self.db.set_cached_audio_file_id(
                source_url,
                message.voice.file_id,
            )

        return message


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


async def _call_with_retry_after(
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
