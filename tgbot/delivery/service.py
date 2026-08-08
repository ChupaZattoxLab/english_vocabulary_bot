"""Reserve and deliver vocabulary cards with Telegram audio-file caching."""

from __future__ import annotations

import asyncio
import html
import logging
from dataclasses import dataclass
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.types import BufferedInputFile, Message

from tgbot.db import Database, ReservedAudio, ReservedCard
from tgbot.delivery.card_template import CardTemplate, CardTemplateError

LOGGER = logging.getLogger("tgbot.delivery")


@dataclass(frozen=True)
class DeliveryOutcome:
    status: str
    card: ReservedCard | None = None


def dialect_caption(dialect: str) -> str:
    return {
        "US": "🇺🇸 US",
        "GB": "🇬🇧 GB",
    }.get(dialect.upper(), dialect.upper())


def voice_caption(dialect: str, ipa: str) -> str:
    label = dialect_caption(dialect)
    transcription = ipa.strip()

    if not transcription:
        return label

    return f"{label} · <code>{html.escape(transcription)}</code>"


def classify_delivery_error(exc: Exception) -> str:
    """Return a stable, queryable category for a delivery exception."""
    if isinstance(exc, TelegramForbiddenError):
        return "bot_blocked"
    if isinstance(exc, CardTemplateError):
        return "template_error"
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    if "timeout" in name or "timeout" in message:
        return "telegram_timeout"
    if "audio" in message or "voice" in message:
        return "audio_unavailable"
    if name.startswith("telegram"):
        return "telegram_error"
    return "technical_error"


class CardDeliveryService:
    def __init__(
        self,
        database: Database,
        template: CardTemplate,
        both_template: CardTemplate | None = None,
    ):
        self.database = database
        self.template = template
        self.both_template = both_template or template

    def render_card(self, card: ReservedCard) -> str:
        dialect_flag = {
            "US": "🇺🇸",
            "GB": "🇬🇧",
            "BOTH": "🇺🇸 + 🇬🇧",
        }.get(card.dialect, "")
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
                "dialect_flag": dialect_flag,
            }
        )

    def reload_templates(self) -> None:
        self.template.reload()
        if self.both_template is not self.template:
            self.both_template.reload()

    async def _send_voice_attachment(
        self,
        bot: Bot,
        *,
        chat_id: int,
        source_url: str,
        audio_data: bytes,
        filename: str,
        caption: str | None,
    ) -> Message:
        async def send(file_reference: str | BufferedInputFile) -> Message:
            try:
                return await bot.send_voice(
                    chat_id=chat_id,
                    voice=file_reference,
                    caption=caption,
                )
            except TelegramRetryAfter as exc:
                LOGGER.warning(
                    "Telegram voice rate limit; retrying in %s seconds",
                    exc.retry_after,
                )
                await asyncio.sleep(float(exc.retry_after))
                return await bot.send_voice(
                    chat_id=chat_id,
                    voice=file_reference,
                    caption=caption,
                )

        method = "voice"
        cached_file_id = await self.database.cached_audio_file_id(
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
                await self.database.clear_cached_audio_file_id(source_url, method)

        upload = BufferedInputFile(audio_data, filename=filename)
        message = await send(upload)
        if message.voice:
            await self.database.cache_audio_file_id(
                source_url,
                method,
                message.voice.file_id,
            )
        return message

    async def _send_card_text(self, bot: Bot, *, chat_id: int, text: str) -> None:
        try:
            await bot.send_message(chat_id=chat_id, text=text)
        except TelegramRetryAfter as exc:
            LOGGER.warning(
                "Telegram text rate limit; retrying in %s seconds",
                exc.retry_after,
            )
            await asyncio.sleep(float(exc.retry_after))
            await bot.send_message(chat_id=chat_id, text=text)

    async def deliver(
        self,
        bot: Bot,
        *,
        telegram_user_id: int,
        chat_id: int,
        scheduled_slot: datetime,
        require_active: bool = True,
    ) -> DeliveryOutcome:
        card = await self.database.reserve_card(
            telegram_user_id,
            scheduled_slot,
            require_active=require_active,
        )
        if card is None:
            return DeliveryOutcome("skipped")

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
            await self.database.finish_delivery(
                card.history_id,
                delivered=True,
                telegram_message_id=message.message_id,
            )
            return DeliveryOutcome("delivered", card)
        except TelegramForbiddenError as exc:
            if text_sent:
                await self.database.finish_delivery(
                    card.history_id,
                    delivered=True,
                )
            else:
                await self.database.finish_delivery(
                    card.history_id,
                    delivered=False,
                    error_type=classify_delivery_error(exc),
                    error_message=str(exc),
                )
            await self.database.deactivate_user(telegram_user_id)
            LOGGER.info("Deactivated unreachable Telegram user %s", telegram_user_id)
            return DeliveryOutcome("delivered" if text_sent else "failed", card)
        except Exception as exc:  # noqa: BLE001
            if text_sent:
                await self.database.finish_delivery(
                    card.history_id,
                    delivered=True,
                )
                LOGGER.exception(
                    "Card voice delivery failed after text for user %s; "
                    "counting as delivered",
                    telegram_user_id,
                )
                return DeliveryOutcome("delivered", card)
            await self.database.finish_delivery(
                card.history_id,
                delivered=False,
                error_type=classify_delivery_error(exc),
                error_message=str(exc),
            )
            LOGGER.exception("Card delivery failed for user %s", telegram_user_id)
            return DeliveryOutcome("failed", card)

    async def _send_reserved_voices(
        self,
        bot: Bot,
        *,
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

    async def _send_reserved(
        self,
        bot: Bot,
        *,
        chat_id: int,
        card: ReservedCard,
    ) -> Message:
        rendered = self.render_card(card)
        await self._send_card_text(bot, chat_id=chat_id, text=rendered)
        return await self._send_reserved_voices(bot, chat_id=chat_id, card=card)

    async def send_preview(
        self, bot: Bot, *, chat_id: int, card: ReservedCard
    ) -> Message:
        """Send a card without creating or changing delivery history."""
        return await self._send_reserved(bot, chat_id=chat_id, card=card)
