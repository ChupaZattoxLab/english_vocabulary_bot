"""Telegram command and callback handlers."""

from __future__ import annotations

from datetime import UTC, datetime

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message, User

from tgbot.config import BotConfig
from tgbot.constants import DELIVERY_STATUS_FAILED, DELIVERY_STATUS_SKIPPED
from tgbot.db import BotUser, Database
from tgbot.delivery import CardDeliveryService
from tgbot.handlers.keyboards import levels_keyboard, pronunciation_keyboard
from tgbot.localization import locale


def create_router(
    database: Database,
    delivery: CardDeliveryService,
    config: BotConfig,
) -> Router:
    router = Router(name="tgbot")

    @router.message(CommandStart())
    async def start_handler(message: Message) -> None:
        if not message.from_user:
            return
        user = await register_user(database, message.from_user, message.chat.id)
        if user.onboarding_completed:
            await message.answer(
                locale.user.welcome_back.format(
                    settings=user_settings_text(user, config)
                )
            )
            return
        await message.answer(
            locale.user.welcome_new.format(cards_per_day=len(config.send_times)),
            reply_markup=levels_keyboard(user.selected_levels),
        )

    @router.message(Command("settings"))
    async def settings_handler(message: Message) -> None:
        if not message.from_user:
            return
        user = await register_user(database, message.from_user, message.chat.id)
        await message.answer(
            user_settings_text(user, config) + locale.user.settings_pick_levels,
            reply_markup=levels_keyboard(user.selected_levels),
        )

    @router.message(Command("levels"))
    async def levels_handler(message: Message) -> None:
        if not message.from_user:
            return
        user = await register_user(database, message.from_user, message.chat.id)
        await message.answer(
            locale.user.pick_levels,
            reply_markup=levels_keyboard(user.selected_levels),
        )

    @router.callback_query(F.data.startswith("level:"))
    async def level_callback(callback: CallbackQuery) -> None:
        action = (callback.data or "").split(":", 1)[1]
        user = await database.get_user(callback.from_user.id)
        if not user:
            await callback.answer(locale.user.need_start, show_alert=True)
            return
        if action == "done":
            if not user.selected_levels:
                await callback.answer(
                    locale.user.need_one_level,
                    show_alert=True,
                )
                return
            message = _callback_message(callback)
            if message is not None:
                await message.edit_text(
                    locale.user.pick_pronunciation_next,
                    reply_markup=pronunciation_keyboard(),
                )
            await callback.answer()
            return

        user = await database.toggle_level(callback.from_user.id, action)
        message = _callback_message(callback)
        if message is not None:
            await message.edit_reply_markup(
                reply_markup=levels_keyboard(user.selected_levels)
            )
        await callback.answer()

    @router.message(Command("pronunciation"))
    async def pronunciation_handler(message: Message) -> None:
        if not message.from_user:
            return
        await register_user(database, message.from_user, message.chat.id)
        await message.answer(
            locale.user.pick_pronunciation,
            reply_markup=pronunciation_keyboard(),
        )

    @router.callback_query(F.data.startswith("dialect:"))
    async def dialect_callback(callback: CallbackQuery) -> None:
        dialect = (callback.data or "").split(":", 1)[1]
        user = await database.get_user(callback.from_user.id)
        if not user:
            await callback.answer(locale.user.need_start, show_alert=True)
            return
        if not user.selected_levels:
            await callback.answer(
                locale.user.need_level_first,
                show_alert=True,
            )
            return
        user = await database.set_pronunciation(callback.from_user.id, dialect)
        message = _callback_message(callback)
        if message is not None:
            await message.edit_text(
                locale.user.onboarding_done.format(
                    settings=user_settings_text(user, config)
                )
            )
        await callback.answer(locale.user.settings_saved)

    @router.message(Command("pause"))
    async def pause_handler(message: Message) -> None:
        if not message.from_user:
            return
        changed = await database.set_active(message.from_user.id, False)
        await message.answer(
            locale.user.paused if changed else locale.user.need_onboarding
        )

    @router.message(Command("resume"))
    async def resume_handler(message: Message) -> None:
        if not message.from_user:
            return
        changed = await database.set_active(message.from_user.id, True)
        await message.answer(
            locale.user.resumed if changed else locale.user.need_onboarding
        )

    @router.message(Command("card"))
    async def card_handler(message: Message) -> None:
        if not message.from_user:
            return
        user = await database.get_user(message.from_user.id)
        if not user or not user.onboarding_completed:
            await message.answer(locale.user.need_onboarding)
            return
        await database.clear_blocked_marker(message.from_user.id)
        bot = message.bot
        if bot is None:
            return
        outcome = await delivery.deliver(
            bot,
            telegram_user_id=message.from_user.id,
            chat_id=message.chat.id,
            scheduled_slot=datetime.now(UTC),
            require_active=False,
        )
        if outcome.status == DELIVERY_STATUS_SKIPPED:
            await message.answer(locale.user.no_cards_left)
            return
        if outcome.status == DELIVERY_STATUS_FAILED:
            await message.answer(locale.user.card_send_failed)
            return
        if not user.is_active:
            await message.answer(locale.user.resume_hint)

    @router.message(Command("help"))
    async def help_handler(message: Message) -> None:
        await message.answer(locale.user.help)

    return router


async def register_user(
    database: Database, telegram_user: User, chat_id: int
) -> BotUser:
    return await database.upsert_user(
        telegram_user_id=telegram_user.id,
        chat_id=chat_id,
        username=telegram_user.username or "",
        first_name=telegram_user.first_name or "",
    )


def user_settings_text(user: BotUser, config: BotConfig) -> str:
    levels = (
        ", ".join(level.upper() for level in user.selected_levels)
        or locale.user.levels_none
    )
    state = (
        locale.user.delivery_active if user.is_active else locale.user.delivery_paused
    )
    return locale.user_settings_lines(
        levels=levels,
        pronunciation=locale.pronunciation_short(user.pronunciation),
        delivery_state=state,
        schedule=config.schedule_text,
    )


def _callback_message(callback: CallbackQuery) -> Message | None:
    message = callback.message
    return message if isinstance(message, Message) else None
