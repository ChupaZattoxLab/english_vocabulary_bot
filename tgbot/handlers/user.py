"""Telegram command and callback handlers."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from aiogram.types import User as AiogramUser

from tgbot.bot_config import BotConfig
from tgbot.db import Database
from tgbot.db.models import (
    VALID_ENGLISH_VARIETY_PREFERENCES,
    VALID_LEVELS,
    CefrLevel,
    EnglishVarietyPreference,
    User,
)
from tgbot.delivery import CardDeliveryService, DeliveryStatus
from tgbot.handlers.helpers import callback_message, format_levels
from tgbot.handlers.keyboard import (
    levels_keyboard,
    pronunciation_keyboard,
    settings_keyboard,
    settings_levels_keyboard,
    settings_pronunciation_keyboard,
)
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
            user_settings_text(user, config),
            reply_markup=settings_keyboard(),
        )

    @router.callback_query(F.data.startswith("settings:"))
    async def settings_callback(callback: CallbackQuery) -> None:
        user = await db.get_user(callback.from_user.id)
        if not user:
            await callback.answer(locale.user.need_start, show_alert=True)
            return

        message = callback_message(callback)
        if message is None:
            await callback.answer()
            return

        _, action, *values = (callback.data or "").split(":", 2)
        value = values[0] if values else ""
        saved = False
        if action in {"open_levels", "levels", "save_levels"}:
            levels = (
                user.settings.selected_levels
                if action == "open_levels"
                else tuple(filter(None, value.split(",")))
            )
            if any(level not in VALID_LEVELS for level in levels):
                await callback.answer()
                return
            levels = tuple(level for level in VALID_LEVELS if level in levels)
            if action == "save_levels":
                if not levels:
                    await callback.answer(locale.user.need_one_level, show_alert=True)
                    return
                user = await db.set_levels(
                    callback.from_user.id, tuple(CefrLevel(level) for level in levels)
                )
                saved = True
            else:
                await message.edit_text(
                    locale.user.settings_choose_levels,
                    reply_markup=settings_levels_keyboard(levels),
                )
                await callback.answer()
                return
        elif action in {"open_pronunciation", "pronunciation", "save_pronunciation"}:
            selected = (
                user.settings.english_variety
                if action == "open_pronunciation"
                else value
            )
            if selected and selected not in VALID_ENGLISH_VARIETY_PREFERENCES:
                await callback.answer()
                return
            if action == "save_pronunciation":
                if not selected:
                    await callback.answer(
                        locale.user.need_pronunciation, show_alert=True
                    )
                    return
                if not user.settings.selected_levels:
                    await callback.answer(locale.user.need_level_first, show_alert=True)
                    return
                user = await db.set_english_variety(
                    callback.from_user.id, EnglishVarietyPreference(selected)
                )
                saved = True
            else:
                current_selection = {
                    button.callback_data
                    for row in (
                        message.reply_markup.inline_keyboard
                        if message.reply_markup is not None
                        else []
                    )
                    for button in row
                }
                if (
                    action == "pronunciation"
                    and f"settings:save_pronunciation:{selected}" in current_selection
                ):
                    await callback.answer()
                    return
                try:
                    await message.edit_text(
                        locale.user.settings_choose_pronunciation,
                        reply_markup=settings_pronunciation_keyboard(selected),
                    )
                except TelegramBadRequest as exc:
                    # Repeated clicks can arrive before the previous edit finishes.
                    if "message is not modified" not in exc.message:
                        raise
                await callback.answer()
                return
        elif action != "back":
            await callback.answer()
            return

        await message.edit_text(
            user_settings_text(user, config), reply_markup=settings_keyboard()
        )
        await callback.answer(locale.user.settings_saved if saved else None)

    @router.callback_query(F.data.startswith("level:"))
    async def level_callback(callback: CallbackQuery) -> None:
        action = (callback.data or "").removeprefix("level:")
        user = await db.get_user(callback.from_user.id)
        if not user:
            await callback.answer(locale.user.need_start, show_alert=True)
            return

        if user.onboarding_completed:
            await callback.answer(locale.user.levels_use_settings, show_alert=True)
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
        if user is None:
            await callback.answer(locale.user.levels_use_settings, show_alert=True)
            return
        if message is not None:
            await message.edit_reply_markup(
                reply_markup=levels_keyboard(user.settings.selected_levels)
            )
        await callback.answer()

    @router.callback_query(
        F.data.startswith("english_variety:") | F.data.startswith("dialect:")
    )
    async def english_variety_callback(callback: CallbackQuery) -> None:
        # Keyboards already sent still use the dialect: callback prefix.
        english_variety = (callback.data or "").split(":", 1)[-1]
        user = await db.get_user(callback.from_user.id)
        if not user:
            await callback.answer(locale.user.need_start, show_alert=True)
            return
        if not user.settings.selected_levels:
            await callback.answer(locale.user.need_level_first, show_alert=True)
            return
        if english_variety not in VALID_ENGLISH_VARIETY_PREFERENCES:
            await callback.answer()
            return

        user = await db.set_english_variety(
            callback.from_user.id,
            EnglishVarietyPreference(english_variety),
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


async def register_user(db: Database, telegram_user: AiogramUser) -> User:
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


def user_settings_text(user: User, config: BotConfig) -> str:
    state = (
        locale.user.delivery_active if user.is_active else locale.user.delivery_paused
    )
    return locale.user_settings_lines(
        levels=format_levels(user.settings.selected_levels, locale.user.levels_none),
        pronunciation=locale.pronunciation_short(user.settings.english_variety),
        delivery_state=state,
        schedule=config.schedule.text,
    )
