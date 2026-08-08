"""Administrator commands for operations, delivery, and content quality."""

from __future__ import annotations

import html
from datetime import UTC, datetime, time, timedelta
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from tgbot.config import BotConfig
from tgbot.db import Database
from tgbot.delivery import CardDeliveryService, CardTemplateError
from tgbot.handlers.admin_keyboards import (
    admin_main_keyboard,
    admin_users_keyboard,
    word_categories_keyboard,
)


def _number(value: Any) -> str:
    return f"{int(value or 0):,}".replace(",", " ")


def _arguments(message: Message) -> str:
    text = message.text or ""
    return text.split(maxsplit=1)[1].strip() if len(text.split(maxsplit=1)) == 2 else ""


def _local_day_bounds(config: BotConfig) -> tuple[datetime, datetime, datetime]:
    local_now = datetime.now(config.timezone)
    local_start = datetime.combine(local_now.date(), time.min, tzinfo=config.timezone)
    return (
        local_now,
        local_start.astimezone(UTC),
        (local_start + timedelta(days=1)).astimezone(UTC),
    )


def _dialect_label(value: str | None) -> str:
    return {
        "us": "American English",
        "gb": "British English",
        "both": "American + British English",
    }.get(value or "", "не выбран")


def _delivery_state(user: dict[str, Any]) -> str:
    if user.get("blocked_at"):
        return "бот заблокирован"
    if user.get("paused_at") or not user.get("is_active"):
        return "приостановлена"
    return "включена"


async def _is_admin(message: Message, config: BotConfig) -> bool:
    if message.from_user and message.from_user.id in config.admin_ids:
        return True
    await message.answer("Нет доступа.")
    return False


async def _render_overview(database: Database, config: BotConfig) -> str:
    local_now, today_start, _ = _local_day_bounds(config)
    users = await database.admin_users_summary(
        today_start=today_start,
        week_start=(local_now - timedelta(days=7)).astimezone(UTC),
        month_start=(local_now - timedelta(days=30)).astimezone(UTC),
    )
    content = await database.admin_content_summary()
    return (
        "<b>🛠 Vocabulary Bot — Admin Panel</b>\n\n"
        f"👥 Пользователей: {_number(users['total_users'])}\n"
        f"📨 Получают карточки: {_number(users['active_users'])}\n"
        f"📚 Готовых карточек: {_number(content['ready_entries'])}\n\n"
    )


async def _render_users(database: Database, config: BotConfig) -> str:
    local_now, today_start, _ = _local_day_bounds(config)
    stats = await database.admin_users_summary(
        today_start=today_start,
        week_start=(local_now - timedelta(days=7)).astimezone(UTC),
        month_start=(local_now - timedelta(days=30)).astimezone(UTC),
    )
    levels = "\n".join(
        f"{level.upper()}: {_number(stats['levels'].get(level, 0))}"
        for level in ("a1", "a2", "b1", "b2", "c1", "c2")
    )
    dialects = (
        ", ".join(
            f"{key.upper()}: {_number(value)}"
            for key, value in sorted(stats["dialects"].items())
        )
        or "нет"
    )
    return (
        "<b>👥 Пользователи</b>\n\n"
        f"Всего: {_number(stats['total_users'])}\n"
        f"Получают карточки: {_number(stats['active_users'])}\n"
        f"Пауза: {_number(stats['paused_users'])}\n"
        f"Заблокировали бота: {_number(stats['blocked_users'])}\n\n"
        "<b>Новые</b>\n"
        f"Сегодня: {_number(stats['new_today'])}\n"
        f"За 7 дней: {_number(stats['new_week'])}\n"
        f"За 30 дней: {_number(stats['new_month'])}\n\n"
        f"<b>По уровням</b>\n{levels}\n\n"
        f"<b>По произношению</b>\n{dialects}"
    )


def create_admin_router(
    *,
    database: Database,
    delivery: CardDeliveryService,
    config: BotConfig,
) -> Router:
    router = Router(name="vocabulary-admin")

    @router.message(Command("admin"))
    async def admin_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return
        await message.answer(
            await _render_overview(database, config),
            reply_markup=admin_main_keyboard(),
        )

    @router.message(Command("users"))
    async def users_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return
        local_now, today_start, _ = _local_day_bounds(config)
        stats = await database.admin_users_summary(
            today_start=today_start,
            week_start=(local_now - timedelta(days=7)).astimezone(UTC),
            month_start=(local_now - timedelta(days=30)).astimezone(UTC),
        )
        levels = "\n".join(
            f"{level.upper()}: {_number(stats['levels'].get(level, 0))}"
            for level in ("a1", "a2", "b1", "b2", "c1", "c2")
        )
        dialects = (
            ", ".join(
                f"{key.upper()}: {_number(value)}"
                for key, value in sorted(stats["dialects"].items())
            )
            or "нет"
        )
        await message.answer(
            "<b>👥 Users</b>\n\n"
            f"Всего: {_number(stats['total_users'])}\n"
            f"Получают карточки: {_number(stats['active_users'])}\n"
            f"Пауза: {_number(stats['paused_users'])}\n"
            f"Заблокировали бота: {_number(stats['blocked_users'])}\n\n"
            "<b>Новые</b>\n"
            f"Сегодня: {_number(stats['new_today'])}\n"
            f"За 7 дней: {_number(stats['new_week'])}\n"
            f"За 30 дней: {_number(stats['new_month'])}\n\n"
            f"<b>По уровням</b>\n{levels}\n\n"
            f"<b>По произношению</b>\n{dialects}"
        )

    @router.message(Command("user"))
    async def user_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return
        argument = _arguments(message)
        if not argument.isdigit():
            await message.answer("Использование: <code>/user TELEGRAM_ID</code>")
            return
        user = await database.admin_user_detail(int(argument))
        if not user:
            await message.answer("Пользователь не найден.")
            return
        registered = user["created_at"].astimezone(config.timezone)
        last_delivery = user.get("last_successful_delivery")
        last_text = (
            last_delivery.astimezone(config.timezone).strftime("%d.%m.%Y %H:%M")
            if last_delivery
            else "ещё не было"
        )
        username = f"@{html.escape(user['username'])}" if user["username"] else "—"
        levels = ", ".join(level.upper() for level in user["selected_levels"]) or "—"
        send_times = ", ".join(t.strftime("%H:%M") for t in config.send_times)
        await message.answer(
            f"<b>👤 User {user['telegram_user_id']}</b>\n\n"
            f"Username: {username}\n"
            f"Зарегистрирован: {registered:%d.%m.%Y %H:%M}\n"
            f"Уровни: {levels}\n"
            f"Произношение: {_dialect_label(user['pronunciation'])}\n"
            f"Карточек в день: {len(config.send_times)}\n"
            f"Время отправки: {send_times}\n"
            f"Часовой пояс: {html.escape(config.timezone.key)}\n"
            f"Рассылка: {_delivery_state(user)}\n\n"
            f"Отправлено карточек: {_number(user['delivered_cards'])}\n"
            f"Последняя отправка: {last_text}\n"
        )

    async def send_word_card(bot: Any, *, chat_id: int, entry_id: int) -> bool:
        card = await database.admin_preview_card(
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
            await message.answer("Использование: <code>/word WORD</code>")
            return
        rows = await database.admin_word_search(word)
        if not rows:
            await message.answer("Слово не найдено.")
            return
        if len(rows) > 1:
            await message.answer(
                f"У слова <b>{html.escape(word)}</b> несколько частей речи. "
                "Выберите нужную:",
                reply_markup=word_categories_keyboard(rows),
            )
            return
        if not await send_word_card(
            message.bot,
            chat_id=message.chat.id,
            entry_id=int(rows[0]["id"]),
        ):
            await message.answer("Для этого слова нет одновременно US и GB аудио.")

    @router.message(Command("send_test"))
    async def send_test_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return
        card = await database.admin_preview_card(random_card=True)
        if not card:
            await message.answer("Нет карточек с готовым аудио для тестовой отправки.")
            return
        await delivery.send_preview(message.bot, chat_id=message.chat.id, card=card)

    @router.message(Command("reload_templates"))
    async def reload_templates_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return
        try:
            delivery.reload_templates()
        except CardTemplateError as exc:
            await message.answer(
                f"Ошибка шаблона: <code>{html.escape(str(exc))}</code>"
            )
            return
        await message.answer("Оба шаблона карточек проверены и перезагружены.")

    @router.callback_query(F.data.startswith("admin:"))
    async def admin_panel_callback(callback: CallbackQuery) -> None:
        if callback.from_user.id not in config.admin_ids:
            await callback.answer("Нет доступа.", show_alert=True)
            return
        if not callback.message:
            await callback.answer("Сообщение панели недоступно.", show_alert=True)
            return

        action = (callback.data or "admin:overview").split(":", 1)[1]
        answered = False
        try:
            if action.startswith("word:"):
                entry_id = action.removeprefix("word:")
                if not entry_id.isdigit():
                    await callback.answer("Некорректный выбор.", show_alert=True)
                    answered = True
                    return
                await callback.answer("Отправляю карточку…")
                answered = True
                if not await send_word_card(
                    callback.bot,
                    chat_id=callback.message.chat.id,
                    entry_id=int(entry_id),
                ):
                    await callback.message.answer(
                        "Для выбранной части речи нет одновременно US и GB аудио."
                    )
                    return
                try:
                    await callback.message.edit_reply_markup(reply_markup=None)
                except TelegramBadRequest:
                    pass
                return

            if action == "test_card":
                await callback.answer("Отправляю тестовую карточку…")
                answered = True
                card = await database.admin_preview_card(random_card=True)
                if not card:
                    await callback.message.answer(
                        "Нет карточек с готовым аудио для предпросмотра."
                    )
                    return
                await delivery.send_preview(
                    callback.bot,
                    chat_id=callback.message.chat.id,
                    card=card,
                )
                return

            if action == "overview":
                text = await _render_overview(database, config)
                keyboard = admin_main_keyboard()
            elif action == "users":
                text = await _render_users(database, config)
                keyboard = admin_users_keyboard()
            else:
                text = await _render_overview(database, config)
                keyboard = admin_main_keyboard()

            try:
                await callback.message.edit_text(text, reply_markup=keyboard)
            except TelegramBadRequest as exc:
                if "message is not modified" not in str(exc).lower():
                    raise
                if not answered:
                    await callback.answer("Данные уже актуальны.")
                    answered = True
        except Exception as exc:  # noqa: BLE001
            if not answered:
                await callback.answer("Не удалось обновить раздел.", show_alert=True)
                answered = True
            await callback.message.answer(
                f"Ошибка admin panel: <code>{html.escape(str(exc)[:300])}</code>"
            )
        finally:
            if not answered:
                await callback.answer()

    return router
