"""Factories for tgbot unit tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.methods import TelegramMethod
from aiogram.types import Message

from tgbot.db.models import (
    AdminUser,
    Card,
    CardAudio,
    EnglishVariety,
    EnglishVarietyVariant,
    UserRole,
    UserSettings,
)

DEFAULT_USER_CARD_ID = uuid.UUID(int=1)
DEFAULT_ENTRY_ID = uuid.UUID(int=10)


def make_audio(
    source_url: str = "https://audio.example/test",
    data: bytes = b"OggS",
    filename: str = "test.voice.ogg",
) -> CardAudio:
    return CardAudio(
        source_url=source_url,
        audio_data=data,
        content_type="audio/ogg",
        filename=filename,
    )


def make_variant(
    english_variety: EnglishVariety = EnglishVariety.US,
    word: str = "color",
    ipa: str = "/ˈkʌlər/",
    audio: CardAudio | None = None,
) -> EnglishVarietyVariant:
    return EnglishVarietyVariant(
        english_variety=english_variety,
        word=word,
        ipa=ipa,
        audio=audio or make_audio(f"https://audio.example/{english_variety}"),
    )


def make_card(
    user_card_id: uuid.UUID = DEFAULT_USER_CARD_ID,
    entry_id: uuid.UUID = DEFAULT_ENTRY_ID,
    word_us: str = "color",
    word_gb: str = "colour",
    lexical_category: str = "noun",
    cefr: str = "B1",
    example: str = "a bright color",
    us: EnglishVarietyVariant | None = None,
    gb: EnglishVarietyVariant | None = None,
    include_us: bool = True,
    include_gb: bool = False,
    us_more: tuple[EnglishVarietyVariant, ...] = (),
    gb_more: tuple[EnglishVarietyVariant, ...] = (),
) -> Card:
    if include_us and us is None:
        us = make_variant(EnglishVariety.US, word_us, "/us/")
    if include_gb and gb is None:
        gb = make_variant(EnglishVariety.GB, word_gb, "/gb/")
    return Card(
        user_card_id=user_card_id,
        entry_id=entry_id,
        word_us=word_us,
        word_gb=word_gb,
        lexical_category=lexical_category,
        cefr=cefr,
        definition="a shade",
        example=example,
        translation="цвет",
        us=us,
        gb=gb,
        us_more=us_more,
        gb_more=gb_more,
    )


def make_admin_user(
    is_active: bool = True,
    paused_at: datetime | None = None,
    blocked_at: datetime | None = None,
) -> AdminUser:
    return AdminUser(
        telegram_user_id=1,
        username="admin",
        role=UserRole.ADMIN,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        settings=UserSettings(selected_levels=("b1",), english_variety=None),
        is_active=is_active,
        onboarding_completed=True,
        paused_at=paused_at,
        blocked_at=blocked_at,
        delivered_cards=0,
        last_successful_delivery=None,
    )


def fake_bot(*, send_voice=None, send_message=None) -> SimpleNamespace:
    return SimpleNamespace(
        send_voice=send_voice or AsyncMock(),
        send_message=send_message
        or AsyncMock(return_value=SimpleNamespace(message_id=1)),
    )


def fake_message(*, text: str | None = None) -> Message:
    return cast(Message, SimpleNamespace(text=text))


def as_bot(bot: SimpleNamespace) -> Bot:
    return cast(Bot, bot)


def fake_delivery_db(**overrides) -> SimpleNamespace:
    defaults = {
        "reserve_card": AsyncMock(return_value=None),
        "finish_delivery": AsyncMock(),
        "deactivate_user": AsyncMock(),
        "get_cached_audio_file_id": AsyncMock(return_value=None),
        "set_cached_audio_file_id": AsyncMock(),
        "clear_cached_audio_file_id": AsyncMock(),
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def telegram_api_error[E: TelegramAPIError](
    exc_type: type[E],
    message: str,
    method: str = "method",
) -> E:
    return exc_type(method=cast(TelegramMethod[Any], method), message=message)


VALID_SINGLE_TEMPLATE = (
    "<b>{word}</b> {lexical_category} {cefr} "
    "{definition} {ipa} {example} {translation} {english_variety}"
)

VALID_BOTH_TEMPLATE = (
    "{word_us} {word_gb} {lexical_category} {cefr} "
    "{definition} {ipa_us} {ipa_gb} {example} {translation}"
)
