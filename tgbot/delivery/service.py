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
from tgbot.db import Database, ReservedAudio, ReservedCard
from tgbot.delivery.card_template import (
    BOTH_CARD_TEMPLATE_PATH,
    CARD_TEMPLATE_PATH,
    CardTemplate,
    CardTemplateError,
)
from tgbot.localization import locale

LOGGER = logging.getLogger("tgbot.delivery")

DeliveryStatus = Literal["delivered", "failed", "skipped"]
T = TypeVar("T")


@dataclass(frozen=True)
class DeliveryOutcome:
    status: DeliveryStatus
    card: ReservedCard | None = None


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
        chat_id: int,
        scheduled_slot: datetime,
        require_active: bool = True,
    ) -> DeliveryOutcome:
        card = await self.db.reserve_card(
            telegram_user_id,
            scheduled_slot,
            require_active=require_active,
        )
        if card is None:
            return DeliveryOutcome(DELIVERY_STATUS_SKIPPED)

        text_sent = False

        try:
            rendered = self.render_card(card)
            await self._send_card_text(bot, chat_id=chat_id, text=rendered)
            text_sent = True

            message = await self._send_reserved_voices(
                bot,
                chat_id=chat_id,
                card=card,
            )
            await self.db.finish_delivery(
                card.history_id,
                delivered=True,
                telegram_message_id=message.message_id,
            )
            return DeliveryOutcome(DELIVERY_STATUS_DELIVERED, card)

        except TelegramForbiddenError as exc:
            if text_sent:
                await self.db.finish_delivery(
                    card.history_id,
                    delivered=True,
                )
            else:
                await self.db.finish_delivery(
                    card.history_id,
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
                    card.history_id,
                    delivered=True,
                )
                LOGGER.exception(
                    "Card voice delivery failed after text for user %s; "
                    "counting as delivered",
                    telegram_user_id,
                )
                return DeliveryOutcome(DELIVERY_STATUS_DELIVERED, card)

            await self.db.finish_delivery(
                card.history_id,
                delivered=False,
                error_type=classify_delivery_error(exc),
                error_message=str(exc),
            )
            LOGGER.exception("Card delivery failed for user %s", telegram_user_id)
            return DeliveryOutcome(DELIVERY_STATUS_FAILED, card)

    async def send_preview(self, bot: Bot, chat_id: int, card: ReservedCard) -> Message:
        """Send a card without creating or changing delivery history."""
        return await self._send_reserved(bot, chat_id=chat_id, card=card)

    def render_card(self, card: ReservedCard) -> str:
        template = self.both_template if card.dialect == "BOTH" else self.template
        return template.render(
            {
                "word": card.word,
                "word_upper": card.word.upper(),
                "word_us": card.word_us or card.word,
                "word_us_upper": (card.word_us or card.word).upper(),
                "word_gb": card.word_gb or card.word,
                "word_gb_upper": (card.word_gb or card.word).upper(),
                "lexical_category": card.lexical_category,
                "cefr": card.cefr,
                "definition": card.definition,
                "ipa": card.ipa,
                "ipa_us": card.ipa_us or card.ipa,
                "ipa_gb": card.ipa_gb or card.ipa,
                "example": card.example,
                "translation": card.translation,
                "dialect": card.dialect,
                "dialect_flag": locale.dialect_flag(card.dialect),
                "heading_definition": locale.labels.card_heading_definition,
                "heading_example": locale.labels.card_heading_example,
                "heading_translation": locale.labels.card_heading_translation,
                "flag_us": locale.labels.dialect_flags["US"],
                "flag_gb": locale.labels.dialect_flags["GB"],
            }
        )

    async def _send_reserved(
        self,
        bot: Bot,
        chat_id: int,
        card: ReservedCard,
    ) -> Message:
        rendered = self.render_card(card)

        await self._send_card_text(bot, chat_id=chat_id, text=rendered)

        return await self._send_reserved_voices(bot, chat_id=chat_id, card=card)

    async def _send_reserved_voices(
        self,
        bot: Bot,
        chat_id: int,
        card: ReservedCard,
    ) -> Message:
        primary_dialect = "US" if card.dialect == "BOTH" else card.dialect

        message = await self._send_voice_attachment(
            bot,
            chat_id=chat_id,
            source_url=card.source_url,
            audio_data=card.audio_data,
            filename=card.filename or f"{card.word}.voice.ogg",
            caption=voice_caption(
                primary_dialect,
                card.ipa_us if card.dialect == "BOTH" else card.ipa,
            ),
        )

        if card.secondary_audio:
            secondary: ReservedAudio = card.secondary_audio

            message = await self._send_voice_attachment(
                bot,
                chat_id=chat_id,
                source_url=secondary.source_url,
                audio_data=secondary.audio_data,
                filename=secondary.filename or f"{card.word}.gb.voice.ogg",
                caption=voice_caption(
                    secondary.dialect,
                    card.ipa_gb,
                ),
            )

        return message

    async def _send_card_text(self, bot: Bot, chat_id: int, text: str) -> None:
        await _call_with_retry_after(
            lambda: bot.send_message(chat_id=chat_id, text=text),
            kind=SEND_KIND_TEXT,
        )

    async def _send_voice_attachment(
        self,
        bot: Bot,
        chat_id: int,
        source_url: str,
        audio_data: bytes,
        filename: str,
        caption: str | None,
    ) -> Message:
        async def send(file_reference: str | BufferedInputFile) -> Message:
            return await _call_with_retry_after(
                lambda: bot.send_voice(
                    chat_id=chat_id,
                    voice=file_reference,
                    caption=caption,
                ),
                kind=SEND_METHOD_VOICE,
            )

        method = SEND_METHOD_VOICE

        cached_file_id = await self.db.cached_audio_file_id(
            source_url,
            method,
        )

        if cached_file_id:
            try:
                return await send(cached_file_id)
            except TelegramBadRequest:
                LOGGER.warning(
                    "Telegram rejected cached file_id for %s; uploading bytes again",
                    source_url,
                )
                await self.db.clear_cached_audio_file_id(source_url, method)

        upload = BufferedInputFile(audio_data, filename=filename)
        message = await send(upload)

        if message.voice:
            await self.db.cache_audio_file_id(
                source_url,
                method,
                message.voice.file_id,
            )

        return message


def voice_caption(dialect: str, ipa: str) -> str:
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
