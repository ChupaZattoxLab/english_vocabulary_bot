"""Telegram command and callback handlers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message, User

from tgbot.bot_config import BotConfig
from tgbot.db import Database
from tgbot.db.models import (
    VALID_DIALECT_PREFERENCES,
    VALID_LEVELS,
    ActiveUser,
    CefrLevel,
    DialectPreference,
)
from tgbot.delivery import CardDeliveryService, DeliveryStatus
from tgbot.handlers.helpers import callback_message, format_levels
from tgbot.handlers.keyboard import levels_keyboard, pronunciation_keyboard
from tgbot.localization import locale


def create_router(
    db: Database,
    delivery: CardDeliveryService,
    config: BotConfig,
) -> Router:
    router = Router(name="tgbot")
    router.message.filter(F.chat.type == ChatType.PRIVATE)
    router.callback_query.filter(F.message.chat.type == ChatType.PRIVATE)

    @router.message(CommandStart())
    async def start_handler(message: Message) -> None:
        if not message.from_user:
            return

        user = await register_user(db, message.from_user)
        if user.onboarding_completed:
            await message.answer(
                locale.user.welcome_back.format(
                    settings=user_settings_text(user, config)
                )
            )
            return

        await message.answer(
            locale.user.welcome_new.format(
                cards_per_day=len(config.schedule.send_times)
            ),
            reply_markup=levels_keyboard(user.settings.selected_levels),
        )

    @router.message(Command("settings"))
    async def settings_handler(message: Message) -> None:
        if not message.from_user:
            return

        user = await register_user(db, message.from_user)
        await message.answer(
            user_settings_text(user, config) + locale.user.settings_pick_levels,
            reply_markup=levels_keyboard(user.settings.selected_levels),
        )

    @router.callback_query(F.data.startswith("level:"))
    async def level_callback(callback: CallbackQuery) -> None:
        action = (callback.data or "").removeprefix("level:")
        user = await db.get_user(callback.from_user.id)
        if not user:
            await callback.answer(locale.user.need_start, show_alert=True)
            return

        message = callback_message(callback)
        if action == "done":
            if not user.settings.selected_levels:
                await callback.answer(locale.user.need_one_level, show_alert=True)
                return
            if message is not None:
                await message.edit_text(
                    locale.user.pick_pronunciation_next,
                    reply_markup=pronunciation_keyboard(),
                )
            await callback.answer()
            return

        if action not in VALID_LEVELS:
            await callback.answer()
            return

        user = await db.toggle_level(callback.from_user.id, CefrLevel(action))
        if message is not None:
            await message.edit_reply_markup(
                reply_markup=levels_keyboard(user.settings.selected_levels)
            )
        await callback.answer()

    @router.callback_query(F.data.startswith("dialect:"))
    async def dialect_callback(callback: CallbackQuery) -> None:
        dialect = (callback.data or "").removeprefix("dialect:")
        user = await db.get_user(callback.from_user.id)
        if not user:
            await callback.answer(locale.user.need_start, show_alert=True)
            return
        if not user.settings.selected_levels:
            await callback.answer(locale.user.need_level_first, show_alert=True)
            return
        if dialect not in VALID_DIALECT_PREFERENCES:
            await callback.answer()
            return

        user = await db.set_dialect(
            callback.from_user.id,
            DialectPreference(dialect),
        )
        message = callback_message(callback)
        if message is not None:
            await message.edit_text(
                locale.user.onboarding_done.format(
                    settings=user_settings_text(user, config)
                )
            )
        await callback.answer(locale.user.settings_saved)

    @router.message(Command("pause"))
    async def pause_handler(message: Message) -> None:
        await set_delivery_active(message, db, False)

    @router.message(Command("resume"))
    async def resume_handler(message: Message) -> None:
        await set_delivery_active(message, db, True)

    @router.message(Command("card"))
    async def card_handler(message: Message) -> None:
        if not message.from_user:
            return

        user = await db.get_user(message.from_user.id)
        if not user or not user.onboarding_completed:
            await message.answer(locale.user.need_onboarding)
            return

        await db.clear_blocked_marker(message.from_user.id)
        bot = message.bot
        if bot is None:
            return

        outcome = await delivery.deliver(bot, message.from_user.id)

        if outcome.status == DeliveryStatus.SKIPPED:
            await message.answer(locale.user.no_cards_left)
            return
        if outcome.status == DeliveryStatus.FAILED:
            await message.answer(locale.user.card_send_failed)
            return
        if not user.is_active:
            await message.answer(locale.user.resume_hint)

    @router.message(Command("help"))
    async def help_handler(message: Message) -> None:
        await message.answer(locale.user.help)

    return router


async def register_user(db: Database, telegram_user: User) -> ActiveUser:
    return await db.upsert_user(
        telegram_user_id=telegram_user.id,
        username=telegram_user.username or "",
    )


async def set_delivery_active(message: Message, db: Database, active: bool) -> None:
    if not message.from_user:
        return

    changed = await db.set_active(message.from_user.id, active)
    if changed:
        text = locale.user.resumed if active else locale.user.paused
    else:
        text = locale.user.need_onboarding
    await message.answer(text)


def user_settings_text(user: ActiveUser, config: BotConfig) -> str:
    state = (
        locale.user.delivery_active if user.is_active else locale.user.delivery_paused
    )
    return locale.user_settings_lines(
        levels=format_levels(user.settings.selected_levels, locale.user.levels_none),
        pronunciation=locale.pronunciation_short(user.settings.dialect),
        delivery_state=state,
        schedule=config.schedule.text,
    )
