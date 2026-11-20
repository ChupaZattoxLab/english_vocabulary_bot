"""Channel subscription: membership, config, the live gate, and delivery."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    CallbackQuery,
    Chat,
    ChatMemberAdministrator,
    ChatMemberBanned,
    ChatMemberLeft,
    ChatMemberMember,
    ChatMemberOwner,
    ChatMemberRestricted,
    Message,
    User,
)

from tests.tgbot.factories import as_bot, telegram_api_error
from tgbot.bot_config import BotConfig, ScheduleSettings
from tgbot.channel_membership import (
    TelegramMembership,
    membership_of,
    telegram_membership,
)
from tgbot.db.models import EnglishVarietyPreference, UserRole, UserSettings
from tgbot.db.models import User as BotUser
from tgbot.delivery import DeliveryStatus
from tgbot.delivery.scheduler import CardScheduler
from tgbot.handlers.keyboard import subscription_keyboard
from tgbot.handlers.subscription import gate_callback, gate_message
from tgbot.handlers.user import create_router
from tgbot.localization import locale
from tgbot.secrets import Secrets


def test_subscribed_statuses() -> None:
    assert (
        membership_of(ChatMemberOwner.model_construct(status=ChatMemberStatus.CREATOR))
        is TelegramMembership.MEMBER
    )
    assert (
        membership_of(
            ChatMemberAdministrator.model_construct(
                status=ChatMemberStatus.ADMINISTRATOR
            )
        )
        is TelegramMembership.MEMBER
    )
    assert (
        membership_of(ChatMemberMember.model_construct(status=ChatMemberStatus.MEMBER))
        is TelegramMembership.MEMBER
    )
    assert (
        membership_of(
            ChatMemberRestricted.model_construct(
                status=ChatMemberStatus.RESTRICTED,
                is_member=True,
            )
        )
        is TelegramMembership.MEMBER
    )


def test_absent_statuses_are_not_members() -> None:
    assert (
        membership_of(ChatMemberLeft.model_construct(status=ChatMemberStatus.LEFT))
        is TelegramMembership.NOT_MEMBER
    )
    assert (
        membership_of(ChatMemberBanned.model_construct(status=ChatMemberStatus.KICKED))
        is TelegramMembership.NOT_MEMBER
    )
    assert (
        membership_of(
            ChatMemberRestricted.model_construct(
                status=ChatMemberStatus.RESTRICTED,
                is_member=False,
            )
        )
        is TelegramMembership.NOT_MEMBER
    )


def test_secrets_do_not_carry_the_channel() -> None:
    loaded = Secrets.load(
        {
            "TELEGRAM_BOT_TOKEN": " token ",
            "OALD_DATABASE_URL": " postgresql+psycopg://127.0.0.1/db ",
            "TELEGRAM_REQUIRED_CHANNEL": "@someone_else",
        }
    )
    assert loaded.telegram_bot_token == "token"
    assert "required_channel" not in type(loaded).model_fields


async def test_middleware_blocks_when_telegram_cannot_answer() -> None:
    bot = SimpleNamespace(
        get_chat_member=AsyncMock(
            side_effect=telegram_api_error(
                TelegramBadRequest, "member list is inaccessible"
            )
        )
    )
    message = _message("/start")
    sent: list[tuple[str, object]] = []

    async def answer(text: str, reply_markup: object = None) -> None:
        sent.append((text, reply_markup))

    object.__setattr__(message, "answer", answer)

    async def handler(event: Message, data: dict[str, object]) -> str:
        return "ran"

    assert await gate_message(handler, message, {"bot": as_bot(bot)}) is None
    assert sent == [(locale.user.subscription_check_failed, None)]


async def test_every_check_asks_telegram() -> None:
    bot = SimpleNamespace(
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="member"))
    )
    assert (
        await telegram_membership(as_bot(bot), "@chan", 7) is TelegramMembership.MEMBER
    )
    assert (
        await telegram_membership(as_bot(bot), "@chan", 7) is TelegramMembership.MEMBER
    )
    assert bot.get_chat_member.await_count == 2


async def test_api_error_is_unknown() -> None:
    bot = SimpleNamespace(
        get_chat_member=AsyncMock(
            side_effect=telegram_api_error(
                TelegramBadRequest, "member list is inaccessible"
            )
        )
    )
    assert (
        await telegram_membership(as_bot(bot), "@chan", 7) is TelegramMembership.UNKNOWN
    )
    assert (
        await telegram_membership(as_bot(bot), "@chan", 7) is TelegramMembership.UNKNOWN
    )
    assert bot.get_chat_member.await_count == 2


def _telegram_user() -> User:
    return User(id=7, is_bot=False, first_name="A")


def _message(text: str) -> Message:
    return Message(
        message_id=1,
        date=datetime(2026, 1, 1, tzinfo=UTC),
        chat=Chat(id=7, type="private"),
        from_user=_telegram_user(),
        text=text,
    )


def _callback(data: str) -> CallbackQuery:
    return CallbackQuery(
        id="cb",
        from_user=_telegram_user(),
        chat_instance="chat",
        data=data,
        message=_message("/start"),
    )


def test_user_router_checks_membership_before_handling() -> None:
    router = create_router(
        db=SimpleNamespace(),
        delivery=SimpleNamespace(),
        config=_config(),
    )

    assert router.message.outer_middleware[0] is gate_message
    assert router.callback_query.outer_middleware[0] is gate_callback


async def test_middleware_blocks_a_non_member_and_offers_the_channel() -> None:
    bot = SimpleNamespace(
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="left"))
    )
    message = _message("/start")
    sent: list[tuple[str, object]] = []

    async def answer(text: str, reply_markup: object = None) -> None:
        sent.append((text, reply_markup))

    object.__setattr__(message, "answer", answer)
    called = False

    async def handler(event: Message, data: dict[str, object]) -> str:
        nonlocal called
        called = True
        return "ran"

    result = await gate_message(handler, message, {"bot": as_bot(bot)})
    assert called is False
    assert result is None
    assert sent
    assert "eng with hanna!" in sent[0][0]
    markup = subscription_keyboard()
    assert sent[0][1] is not None
    assert markup.inline_keyboard[0][0].url == "https://t.me/engwithhanna"


async def test_middleware_lets_a_member_through() -> None:
    bot = SimpleNamespace(
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="member"))
    )

    async def handler(event: object, data: dict[str, object]) -> str:
        return "ran"

    assert await gate_message(handler, _message("/card"), {"bot": as_bot(bot)}) == "ran"
    bot.get_chat_member.assert_awaited()


async def test_middleware_answers_a_callback_without_opening_the_handler() -> None:
    bot = SimpleNamespace(
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="left"))
    )
    callback = _callback("level:a1")
    alerts: list[tuple[object, bool]] = []

    async def answer(
        text: object = None, show_alert: bool = False, **kwargs: object
    ) -> None:
        alerts.append((text, show_alert))

    object.__setattr__(callback, "answer", answer)
    if isinstance(callback.message, Message):

        async def message_answer(*args: object, **kwargs: object) -> None:
            return None

        object.__setattr__(callback.message, "answer", message_answer)
    called = False

    async def handler(event: object, data: dict[str, object]) -> None:
        nonlocal called
        called = True

    await gate_callback(handler, callback, {"bot": as_bot(bot)})
    assert called is False
    assert alerts and alerts[0][1] is True


def _schedule() -> ScheduleSettings:
    return ScheduleSettings(
        timezone=ZoneInfo("Europe/Moscow"),
        send_times=(time(13, 0),),
        text="13:00",
        poll_seconds=20,
        delivery_concurrency=5,
        grace_minutes=60,
    )


def _config() -> BotConfig:
    return BotConfig(
        bot_token="token",
        db_url="postgresql+psycopg://127.0.0.1/db",
        db_pool_size=1,
        schedule=_schedule(),
    )


def _bot_user() -> BotUser:
    return BotUser(
        telegram_user_id=7,
        username="u",
        role=UserRole.USER,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        settings=UserSettings(
            selected_levels=("a1",),
            english_variety=EnglishVarietyPreference.US,
        ),
        is_active=True,
        onboarding_completed=True,
        paused_at=None,
        blocked_at=None,
    )


def _scheduler() -> tuple[CardScheduler, AsyncMock]:
    deliver = AsyncMock(return_value=SimpleNamespace(status=DeliveryStatus.DELIVERED))
    scheduler = CardScheduler(
        db=SimpleNamespace(),
        delivery=SimpleNamespace(deliver=deliver),
        config=_config(),
    )
    return scheduler, deliver


async def test_scheduler_skips_a_non_member_and_sends_to_a_member() -> None:
    left = SimpleNamespace(
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="left"))
    )
    scheduler, deliver = _scheduler()
    status = await scheduler.deliver_to_user(
        as_bot(left),
        _bot_user(),
        datetime(2026, 1, 1, tzinfo=UTC),
        asyncio.Semaphore(1),
    )
    assert status is DeliveryStatus.SKIPPED
    deliver.assert_not_awaited()

    member = SimpleNamespace(
        get_chat_member=AsyncMock(return_value=SimpleNamespace(status="member"))
    )
    scheduler, deliver = _scheduler()
    status = await scheduler.deliver_to_user(
        as_bot(member),
        _bot_user(),
        datetime(2026, 1, 1, tzinfo=UTC),
        asyncio.Semaphore(1),
    )
    assert status is DeliveryStatus.DELIVERED
    deliver.assert_awaited()


def test_subscribe_prompt_names_the_channel() -> None:
    assert "eng with hanna!" in locale.user.need_subscription
    assert locale.keyboard.subscribe
    assert locale.keyboard.subscribed
