"""CardDeliveryService behaviour with mocked Bot/DB."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.types import BufferedInputFile

from tests.tgbot.factories import (
    VALID_BOTH_TEMPLATE,
    VALID_SINGLE_TEMPLATE,
    fake_bot,
    fake_delivery_db,
    make_audio,
    make_card,
    make_variant,
)
from tgbot.db.models import Dialect
from tgbot.delivery import DeliveryStatus
from tgbot.delivery.service import CardDeliveryService


@pytest.fixture
def templates(tmp_path: Path) -> tuple[Path, Path]:
    single = tmp_path / "card.html"
    both = tmp_path / "both.html"
    single.write_text(VALID_SINGLE_TEMPLATE, encoding="utf-8")
    both.write_text(VALID_BOTH_TEMPLATE, encoding="utf-8")
    return single, both


def _service(db, templates: tuple[Path, Path]) -> CardDeliveryService:
    single, both = templates
    with (
        patch("tgbot.delivery.service.CARD_TEMPLATE_PATH", single),
        patch("tgbot.delivery.service.BOTH_CARD_TEMPLATE_PATH", both),
    ):
        return CardDeliveryService(db)


@pytest.mark.asyncio
async def test_deliver_skips_when_no_card_reserved(templates) -> None:
    service = _service(fake_delivery_db(), templates)
    outcome = await service.deliver(fake_bot(), 1)
    assert outcome.status == DeliveryStatus.SKIPPED
    assert outcome.card is None


@pytest.mark.asyncio
async def test_voice_upload_caches_telegram_file_id(templates) -> None:
    card = make_card()
    db = fake_delivery_db()
    bot = fake_bot(
        send_voice=AsyncMock(
            return_value=SimpleNamespace(
                message_id=10,
                voice=SimpleNamespace(file_id="tg-file"),
            )
        ),
        send_message=AsyncMock(),
    )
    service = _service(db, templates)

    await service.send_card(bot, 123, card)

    bot.send_message.assert_awaited_once()
    bot.send_voice.assert_awaited_once()
    voice_arg = bot.send_voice.await_args.kwargs["voice"]
    assert isinstance(voice_arg, BufferedInputFile)
    assert voice_arg.filename == card.primary.audio.filename
    db.set_cached_audio_file_id.assert_awaited_once_with(
        card.primary.audio.source_url,
        "tg-file",
    )


@pytest.mark.asyncio
async def test_cached_file_id_is_cleared_on_bad_request(templates) -> None:
    card = make_card()
    db = fake_delivery_db(get_cached_audio_file_id=AsyncMock(return_value="stale"))
    bot = fake_bot(
        send_voice=AsyncMock(
            side_effect=[
                TelegramBadRequest(method="sendVoice", message="bad file"),
                SimpleNamespace(
                    message_id=11,
                    voice=SimpleNamespace(file_id="fresh"),
                ),
            ]
        ),
        send_message=AsyncMock(),
    )
    service = _service(db, templates)

    await service.send_card(bot, 1, card)

    db.clear_cached_audio_file_id.assert_awaited_once_with(
        card.primary.audio.source_url
    )
    db.set_cached_audio_file_id.assert_awaited_once_with(
        card.primary.audio.source_url,
        "fresh",
    )


@pytest.mark.asyncio
async def test_partial_send_counts_as_delivered(templates) -> None:
    """Text succeeded, voice failed → still delivered (card text reached user)."""
    card = make_card()
    db = fake_delivery_db(reserve_card=AsyncMock(return_value=card))
    bot = fake_bot(
        send_message=AsyncMock(),
        send_voice=AsyncMock(side_effect=RuntimeError("voice failed")),
    )
    service = _service(db, templates)

    outcome = await service.deliver(bot, 1, datetime.now(UTC))

    assert outcome.status == DeliveryStatus.DELIVERED
    db.finish_delivery.assert_awaited_once_with(card.user_card_id, delivered=True)


@pytest.mark.asyncio
async def test_forbidden_before_text_fails_and_deactivates(templates) -> None:
    card = make_card()
    db = fake_delivery_db(reserve_card=AsyncMock(return_value=card))
    bot = fake_bot(
        send_message=AsyncMock(
            side_effect=TelegramForbiddenError(
                method="sendMessage",
                message="blocked",
            )
        )
    )
    service = _service(db, templates)

    outcome = await service.deliver(bot, 99)

    assert outcome.status == DeliveryStatus.FAILED
    db.deactivate_user.assert_awaited_once_with(99)


@pytest.mark.asyncio
async def test_both_dialects_send_two_voices(templates) -> None:
    card = make_card(
        include_us=True,
        include_gb=True,
        us=make_variant(
            Dialect.US,
            "color",
            "/us/",
            make_audio("https://a/us", filename="us.voice.ogg"),
        ),
        gb=make_variant(
            Dialect.GB,
            "colour",
            "/gb/",
            make_audio("https://a/gb", filename="gb.voice.ogg"),
        ),
    )
    db = fake_delivery_db()
    bot = fake_bot(
        send_voice=AsyncMock(
            side_effect=[
                SimpleNamespace(message_id=1, voice=SimpleNamespace(file_id="us-id")),
                SimpleNamespace(message_id=2, voice=SimpleNamespace(file_id="gb-id")),
            ]
        ),
        send_message=AsyncMock(),
    )
    service = _service(db, templates)

    await service.send_card(bot, 1, card)

    assert bot.send_voice.await_count == 2
    assert bot.send_message.await_count == 1
