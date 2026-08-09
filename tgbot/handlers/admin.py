"""Administrator commands for operations, delivery, and content quality."""

from __future__ import annotations

import html
from datetime import UTC, datetime, time, timedelta

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from tgbot.bot_config import BotConfig
from tgbot.constants import ADMIN_STATS_MONTH_DAYS, ADMIN_STATS_WEEK_DAYS
from tgbot.db import Database
from tgbot.db.models import VALID_LEVELS, AdminUserDetail
from tgbot.delivery import CardDeliveryService
from tgbot.handlers.admin_keyboards import (
    admin_main_keyboard,
    admin_users_keyboard,
    word_categories_keyboard,
)
from tgbot.localization import locale


def create_admin_router(
    db: Database,
    delivery: CardDeliveryService,
    config: BotConfig,
) -> Router:
    router = Router(name="tgbot-admin")

    @router.message(Command("admin"))
    async def admin_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return

        await message.answer(
            await _render_overview(db, config),
            reply_markup=admin_main_keyboard(),
        )

    @router.message(Command("stats"))
    async def stats_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return

        await message.answer(await _render_users(db, config))

    @router.message(Command("user"))
    async def user_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return

        argument = _arguments(message)

        if not argument.isdigit():
            await message.answer(locale.admin.user_usage)
            return

        user = await db.admin_user_detail(int(argument))

        if not user:
            await message.answer(locale.admin.user_not_found)
            return

        registered = user.created_at.astimezone(config.schedule.timezone)
        last_text = (
            user.last_successful_delivery.astimezone(config.schedule.timezone).strftime(
                "%d.%m.%Y %H:%M"
            )
            if user.last_successful_delivery
            else locale.admin.never_delivered
        )
        username = (
            f"@{html.escape(user.username)}"
            if user.username
            else locale.admin.placeholder
        )
        levels = (
            ", ".join(level.upper() for level in user.selected_levels)
            or locale.admin.placeholder
        )
        send_times = ", ".join(
            t.strftime("%H:%M") for t in config.schedule.send_times
        )

        await message.answer(
            locale.admin.user_detail.format(
                telegram_user_id=user.telegram_user_id,
                username=username,
                registered=registered.strftime("%d.%m.%Y %H:%M"),
                levels=levels,
                pronunciation=locale.pronunciation_admin(user.pronunciation),
                cards_per_day=len(config.schedule.send_times),
                send_times=send_times,
                timezone=html.escape(config.schedule.timezone.key),
                delivery_state=_delivery_state(user),
                delivered_cards=_number(user.delivered_cards),
                last_delivery=last_text,
            )
        )

    async def send_word_card(bot: Bot, chat_id: int, entry_id: int) -> bool:
        card = await db.admin_preview_card(
            entry_id=entry_id,
            dialect="both",
        )
        if not card:
            return False

        await delivery.send_preview(bot, chat_id=chat_id, card=card)

        return True

    @router.message(Command("word"))
    async def word_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return

        word = _arguments(message)

        if not word:
            await message.answer(locale.admin.word_usage)
            return

        rows = await db.admin_word_search(word)

        if not rows:
            await message.answer(locale.admin.word_not_found)
            return

        if len(rows) > 1:
            await message.answer(
                locale.admin.word_pick_category.format(word=html.escape(word)),
                reply_markup=word_categories_keyboard(rows),
            )
            return

        assert len(rows) == 1
        match = rows[0]
        bot = message.bot

        if bot is None:
            return

        if not await send_word_card(
            bot,
            chat_id=message.chat.id,
            entry_id=match.id,
        ):
            await message.answer(locale.admin.word_no_both_audio)

    @router.callback_query(F.data.startswith("admin:"))
    async def admin_panel_callback(callback: CallbackQuery) -> None:
        if callback.from_user.id not in config.admin_ids:
            await callback.answer(locale.admin.no_access, show_alert=True)
            return

        panel_message = _callback_message(callback)

        if panel_message is None:
            await callback.answer(locale.admin.panel_unavailable, show_alert=True)
            return

        action = (callback.data or "admin:overview").split(":", 1)[1]
        answered = False

        try:
            if action.startswith("word:"):
                entry_id = action.removeprefix("word:")

                if not entry_id.isdigit():
                    await callback.answer(locale.admin.bad_choice, show_alert=True)
                    answered = True
                    return

                await callback.answer(locale.admin.sending_card)
                answered = True

                bot = callback.bot

                if bot is None:
                    return

                if not await send_word_card(
                    bot,
                    chat_id=panel_message.chat.id,
                    entry_id=int(entry_id),
                ):
                    await panel_message.answer(locale.admin.word_entry_no_both_audio)
                    return

                try:
                    await panel_message.edit_reply_markup(reply_markup=None)
                except TelegramBadRequest:
                    pass
                return

            if action == "overview":
                text = await _render_overview(db, config)
                keyboard = admin_main_keyboard()
            elif action == "users":
                text = await _render_users(db, config)
                keyboard = admin_users_keyboard()
            else:
                text = await _render_overview(db, config)
                keyboard = admin_main_keyboard()

            try:
                await panel_message.edit_text(text, reply_markup=keyboard)
            except TelegramBadRequest as exc:
                if "message is not modified" not in str(exc).lower():
                    raise
                if not answered:
                    await callback.answer(locale.admin.already_up_to_date)
                    answered = True

        except Exception as exc:  # noqa: BLE001
            if not answered:
                await callback.answer(
                    locale.admin.panel_update_failed,
                    show_alert=True,
                )
                answered = True
            await panel_message.answer(
                locale.admin.panel_error.format(error=html.escape(str(exc)[:300]))
            )

        finally:
            if not answered:
                await callback.answer()

    return router


async def _is_admin(message: Message, config: BotConfig) -> bool:
    if message.from_user and message.from_user.id in config.admin_ids:
        return True

    await message.answer(locale.admin.no_access)

    return False


async def _render_overview(db: Database, config: BotConfig) -> str:
    local_now, today_start = _local_day_bounds(config)

    users = await db.admin_users_summary(
        today_start=today_start,
        week_start=(local_now - timedelta(days=ADMIN_STATS_WEEK_DAYS)).astimezone(UTC),
        month_start=(local_now - timedelta(days=ADMIN_STATS_MONTH_DAYS)).astimezone(
            UTC
        ),
    )
    content = await db.admin_content_summary()

    return locale.admin.overview.format(
        total_users=_number(users.total_users),
        active_users=_number(users.active_users),
        ready_entries=_number(content.ready_entries),
    )


async def _render_users(db: Database, config: BotConfig) -> str:
    local_now, today_start = _local_day_bounds(config)

    stats = await db.admin_users_summary(
        today_start=today_start,
        week_start=(local_now - timedelta(days=ADMIN_STATS_WEEK_DAYS)).astimezone(UTC),
        month_start=(local_now - timedelta(days=ADMIN_STATS_MONTH_DAYS)).astimezone(
            UTC
        ),
    )

    levels = "\n".join(
        f"{level.upper()}: {_number(stats.levels.get(level, 0))}"
        for level in VALID_LEVELS
    )
    dialects = (
        ", ".join(
            f"{key.upper()}: {_number(value)}"
            for key, value in sorted(stats.dialects.items())
        )
        or locale.admin.none
    )

    return locale.admin.users_panel.format(
        total_users=_number(stats.total_users),
        active_users=_number(stats.active_users),
        paused_users=_number(stats.paused_users),
        blocked_users=_number(stats.blocked_users),
        new_today=_number(stats.new_today),
        new_week=_number(stats.new_week),
        new_month=_number(stats.new_month),
        week_days=ADMIN_STATS_WEEK_DAYS,
        month_days=ADMIN_STATS_MONTH_DAYS,
        levels=levels,
        dialects=dialects,
    )


def _local_day_bounds(config: BotConfig) -> tuple[datetime, datetime]:
    local_now = datetime.now(config.schedule.timezone)
    local_start = datetime.combine(
        local_now.date(), time.min, tzinfo=config.schedule.timezone
    )

    return (
        local_now,
        local_start.astimezone(UTC),
    )


def _delivery_state(user: AdminUserDetail) -> str:
    if user.blocked_at:
        return locale.admin.delivery_blocked
    if user.paused_at or not user.is_active:
        return locale.admin.delivery_paused
    return locale.admin.delivery_active


def _arguments(message: Message) -> str:
    text = message.text or ""

    return text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) == 2 else ""


def _number(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def _callback_message(callback: CallbackQuery) -> Message | None:
    message = callback.message

    return message if isinstance(message, Message) else None
