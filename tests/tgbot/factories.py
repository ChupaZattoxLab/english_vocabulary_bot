"""Factories for tgbot unit tests."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from tgbot.db.models import (
    AdminUser,
    Card,
    CardAudio,
    Dialect,
    DialectVariant,
    UserRole,
    UserSettings,
)


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
    dialect: Dialect = Dialect.US,
    word: str = "color",
    ipa: str = "/ˈkʌlər/",
    audio: CardAudio | None = None,
) -> DialectVariant:
    return DialectVariant(
        dialect=dialect,
        word=word,
        ipa=ipa,
        audio=audio or make_audio(f"https://audio.example/{dialect}"),
    )


def make_card(
    user_card_id: int = 1,
    entry_id: int = 10,
    word_us: str = "color",
    word_gb: str = "colour",
    us: DialectVariant | None = None,
    gb: DialectVariant | None = None,
    include_us: bool = True,
    include_gb: bool = False,
) -> Card:
    if include_us and us is None:
        us = make_variant(Dialect.US, word_us, "/us/")
    if include_gb and gb is None:
        gb = make_variant(Dialect.GB, word_gb, "/gb/")
    return Card(
        user_card_id=user_card_id,
        entry_id=entry_id,
        word_us=word_us,
        word_gb=word_gb,
        lexical_category="noun",
        cefr="B1",
        definition="a shade",
        example="a bright color",
        translation="цвет",
        us=us,
        gb=gb,
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
        settings=UserSettings(selected_levels=("b1",), dialect=None),
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
        send_message=send_message or AsyncMock(),
    )


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


VALID_SINGLE_TEMPLATE = (
    "<b>{word}</b> {lexical_category} {cefr} "
    "{definition} {ipa} {example} {translation} {dialect}"
)

VALID_BOTH_TEMPLATE = (
    "{word_us} {word_gb} {lexical_category} {cefr} "
    "{definition} {ipa_us} {ipa_gb} {example} {translation}"
)
