"""Telegram command and callback handlers."""

from __future__ import annotations

from datetime import datetime, timezone

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message, User

from vocabulary_bot.config import BotConfig
from vocabulary_bot.database import BotUser, Database
from vocabulary_bot.delivery import CardDeliveryService
from vocabulary_bot.keyboards import levels_keyboard, pronunciation_keyboard


def user_settings_text(user: BotUser, config: BotConfig) -> str:
    levels = ", ".join(level.upper() for level in user.selected_levels) or "не выбраны"
    dialect = {
        "us": "US",
        "gb": "GB",
        "both": "US + GB",
    }.get(user.pronunciation or "", "не выбрано")
    state = "активна" if user.is_active else "приостановлена"
    return (
        f"<b>Ваши настройки</b>\n"
        f"Уровни: {levels}\n"
        f"Произношение: {dialect}\n"
        f"Рассылка: {state}\n"
        f"Время: {config.schedule_text}"
    )


async def register_user(database: Database, telegram_user: User, chat_id: int) -> BotUser:
    return await database.upsert_user(
        telegram_user_id=telegram_user.id,
        chat_id=chat_id,
        username=telegram_user.username or "",
        first_name=telegram_user.first_name or "",
    )


def create_router(
    *,
    database: Database,
    delivery: CardDeliveryService,
    config: BotConfig,
) -> Router:
    router = Router(name="vocabulary-bot")

    @router.message(CommandStart())
    async def start_handler(message: Message) -> None:
        if not message.from_user:
            return
        user = await register_user(database, message.from_user, message.chat.id)
        if user.onboarding_completed:
            await message.answer(
                "С возвращением!\n\n" + user_settings_text(user, config)
            )
            return
        await message.answer(
            "Привет! Я буду присылать три новые английские карточки в день.\n\n"
            "Сначала выберите один или несколько уровней CEFR:",
            reply_markup=levels_keyboard(user.selected_levels),
        )

    @router.message(Command("settings"))
    async def settings_handler(message: Message) -> None:
        if not message.from_user:
            return
        user = await register_user(database, message.from_user, message.chat.id)
        await message.answer(
            user_settings_text(user, config)
            + "\n\nВыберите уровни. Можно отметить несколько:",
            reply_markup=levels_keyboard(user.selected_levels),
        )

    @router.message(Command("levels"))
    async def levels_handler(message: Message) -> None:
        if not message.from_user:
            return
        user = await register_user(database, message.from_user, message.chat.id)
        await message.answer(
            "Выберите один или несколько уровней CEFR:",
            reply_markup=levels_keyboard(user.selected_levels),
        )

    @router.callback_query(F.data.startswith("level:"))
    async def level_callback(callback: CallbackQuery) -> None:
        action = (callback.data or "").split(":", 1)[1]
        user = await database.get_user(callback.from_user.id)
        if not user:
            await callback.answer("Сначала отправьте /start", show_alert=True)
            return
        if action == "done":
            if not user.selected_levels:
                await callback.answer(
                    "Выберите хотя бы один уровень",
                    show_alert=True,
                )
                return
            if callback.message:
                await callback.message.edit_text(
                    "Теперь выберите произношение для карточек:",
                    reply_markup=pronunciation_keyboard(),
                )
            await callback.answer()
            return

        user = await database.toggle_level(callback.from_user.id, action)
        if callback.message:
            await callback.message.edit_reply_markup(
                reply_markup=levels_keyboard(user.selected_levels)
            )
        await callback.answer()

    @router.message(Command("pronunciation"))
    async def pronunciation_handler(message: Message) -> None:
        if not message.from_user:
            return
        await register_user(database, message.from_user, message.chat.id)
        await message.answer(
            "Какое произношение использовать?",
            reply_markup=pronunciation_keyboard(),
        )

    @router.callback_query(F.data.startswith("dialect:"))
    async def dialect_callback(callback: CallbackQuery) -> None:
        dialect = (callback.data or "").split(":", 1)[1]
        user = await database.get_user(callback.from_user.id)
        if not user:
            await callback.answer("Сначала отправьте /start", show_alert=True)
            return
        if not user.selected_levels:
            await callback.answer(
                "Сначала выберите хотя бы один уровень",
                show_alert=True,
            )
            return
        user = await database.set_pronunciation(callback.from_user.id, dialect)
        if callback.message:
            await callback.message.edit_text(
                "Настройка завершена!\n\n"
                + user_settings_text(user, config)
                + "\n\nДля проверки можно запросить /card."
            )
        await callback.answer("Настройки сохранены")

    @router.message(Command("pause"))
    async def pause_handler(message: Message) -> None:
        if not message.from_user:
            return
        changed = await database.set_active(message.from_user.id, False)
        await message.answer(
            "Рассылка приостановлена. Команда для продолжения: /resume"
            if changed
            else "Сначала завершите настройку через /start."
        )

    @router.message(Command("resume"))
    async def resume_handler(message: Message) -> None:
        if not message.from_user:
            return
        changed = await database.set_active(message.from_user.id, True)
        await message.answer(
            "Рассылка снова активна."
            if changed
            else "Сначала завершите настройку через /start."
        )

    @router.message(Command("card"))
    async def card_handler(message: Message) -> None:
        if not message.from_user:
            return
        user = await database.get_user(message.from_user.id)
        if not user or not user.onboarding_completed:
            await message.answer("Сначала завершите настройку через /start.")
            return
        outcome = await delivery.deliver(
            message.bot,
            telegram_user_id=message.from_user.id,
            chat_id=message.chat.id,
            scheduled_slot=datetime.now(timezone.utc),
        )
        if outcome.status == "skipped":
            await message.answer(
                "Для выбранных уровней больше нет новых карточек с загруженным "
                "аудио. Карточки не повторяются."
            )

    @router.message(Command("help"))
    async def help_handler(message: Message) -> None:
        await message.answer(
            "<b>Команды</b>\n"
            "/start — регистрация\n"
            "/settings — все настройки\n"
            "/levels — уровни CEFR\n"
            "/pronunciation — US или GB\n"
            "/card — получить карточку сейчас\n"
            "/pause — приостановить рассылку\n"
            "/resume — продолжить рассылку\n"
            "/help — эта справка"
        )

    return router
