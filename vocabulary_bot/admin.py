"""Administrator commands for operations, delivery, and content quality."""

from __future__ import annotations

import html
from datetime import datetime, time, timedelta, timezone
from time import perf_counter
from typing import Any

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from vocabulary_bot.admin_keyboards import (
    admin_audio_keyboard,
    admin_errors_keyboard,
    admin_health_keyboard,
    admin_list_keyboard,
    admin_main_keyboard,
    admin_users_keyboard,
)
from vocabulary_bot.card_template import CardTemplateError
from vocabulary_bot.config import BotConfig
from vocabulary_bot.database import Database
from vocabulary_bot.delivery import CardDeliveryService, classify_delivery_error


ERROR_LABELS = {
    "audio_unavailable": "Audio unavailable",
    "bot_blocked": "Bot blocked",
    "telegram_error": "Telegram error",
    "telegram_timeout": "Telegram timeout",
    "technical_error": "Technical error",
    "template_error": "Template error",
    "unknown": "Unknown",
}


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
        local_start.astimezone(timezone.utc),
        (local_start + timedelta(days=1)).astimezone(timezone.utc),
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


def _translation_exists(value: Any) -> bool:
    translations = value or {}
    russian = translations.get("ru") or {}
    return bool(str(russian.get("main") or "").strip()) or any(
        str(item).strip() for item in russian.get("also") or []
    )


async def _is_admin(message: Message, config: BotConfig) -> bool:
    if message.from_user and message.from_user.id in config.admin_ids:
        return True
    await message.answer("Нет доступа.")
    return False


async def _render_overview(database: Database, config: BotConfig) -> str:
    local_now, today_start, today_end = _local_day_bounds(config)
    users = await database.admin_users_summary(
        today_start=today_start,
        week_start=(local_now - timedelta(days=7)).astimezone(timezone.utc),
        month_start=(local_now - timedelta(days=30)).astimezone(timezone.utc),
    )
    delivery_stats = await database.admin_delivery_summary(
        start=today_start,
        end=today_end,
    )
    content = await database.admin_content_summary()
    system = await database.admin_system_summary(
        since=datetime.now(timezone.utc) - timedelta(hours=24)
    )
    last_delivered = system.get("last_delivered_cards")
    last_failed = system.get("last_failed_cards")
    last_delivery = (
        f"✅ Успешно: {_number(last_delivered)}\n"
        f"❌ Ошибок: {_number(last_failed)}"
        if last_delivered is not None
        else "ещё не было"
    )
    return (
        "<b>🛠 Vocabulary Bot — Admin Panel</b>\n\n"
        f"👥 Пользователей: {_number(users['total_users'])}\n"
        f"📨 Получают карточки: {_number(users['active_users'])}\n"
        f"📚 Готовых карточек: {_number(content['ready_entries'])}\n\n"
        f"<b>Последняя рассылка</b>\n{last_delivery}\n\n"
        f"Сегодня отправлено карточек: {_number(delivery_stats['cards_sent'])}"
    )


async def _render_users(database: Database, config: BotConfig) -> str:
    local_now, today_start, _ = _local_day_bounds(config)
    stats = await database.admin_users_summary(
        today_start=today_start,
        week_start=(local_now - timedelta(days=7)).astimezone(timezone.utc),
        month_start=(local_now - timedelta(days=30)).astimezone(timezone.utc),
    )
    levels = "\n".join(
        f"{level.upper()}: {_number(stats['levels'].get(level, 0))}"
        for level in ("a1", "a2", "b1", "b2", "c1", "c2")
    )
    dialects = ", ".join(
        f"{key.upper()}: {_number(value)}"
        for key, value in sorted(stats["dialects"].items())
    ) or "нет"
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


async def _render_audio(database: Database) -> str:
    stats = await database.admin_audio_summary(
        since=datetime.now(timezone.utc) - timedelta(hours=24)
    )
    return (
        "<b>🔊 Аудио</b>\n\n"
        f"Всего активных карточек: {_number(stats['total_entries'])}\n"
        f"С US audio: {_number(stats['with_us_audio'])}\n"
        f"С UK audio: {_number(stats['with_gb_audio'])}\n"
        f"Без обоих вариантов: {_number(stats['without_audio'])}\n\n"
        f"Готовых OGG Opus: {_number(stats['prepared_voice_files'])}\n"
        f"Сохранён Telegram file_id: {_number(stats['cached_telegram_files'])}\n"
        f"Ещё не загружались в Telegram: {_number(stats['not_cached_telegram_files'])}\n"
        f"Ошибок скачивания за 24 часа: {_number(stats['download_errors_24h'])}\n"
        f"URL со статусом failed: {_number(stats['failed_source_urls'])}"
    )


async def _render_failed(database: Database, config: BotConfig) -> str:
    rows = await database.admin_failed_deliveries(
        start=datetime.now(timezone.utc) - timedelta(days=7)
    )
    if not rows:
        return "<b>❌ Ошибки доставки</b>\n\nЗа последние 7 дней ошибок нет."
    lines = []
    for row in rows:
        occurred = row["scheduled_slot"].astimezone(config.timezone)
        reason = ERROR_LABELS.get(
            row["error_type"] or "unknown",
            row["error_type"] or "Unknown",
        )
        lines.append(
            f"#{row['id']} · {occurred:%d.%m %H:%M} · user {row['telegram_user_id']} · "
            f"word {row['entry_id']} ({html.escape(row['word_us'])}) · {html.escape(reason)}"
        )
    return "<b>❌ Ошибки доставки за 7 дней</b>\n\n" + "\n".join(lines)


async def _render_errors(database: Database) -> str:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    system = await database.admin_system_summary(since=since)
    rows = await database.admin_failed_deliveries(start=since, limit=10)
    lines = "\n".join(
        f"#{row['id']} · {ERROR_LABELS.get(row['error_type'] or 'unknown', row['error_type'] or 'Unknown')} · "
        f"{html.escape(str(row['error_message'])[:120])}"
        for row in rows
    ) or "нет"
    return (
        "<b>⚠️ Ошибки — 24 часа</b>\n\n"
        f"Всего: {_number(system['errors'])}\n\n"
        f"<b>Последние ошибки доставки</b>\n{lines}"
    )


async def _render_missing_audio(database: Database) -> str:
    stats = await database.admin_content_summary()
    rows = await database.admin_missing_entries(audio_only=True)
    samples = "\n".join(
        f"#{row['id']} · {html.escape(row['word_us'])} · {html.escape(row['lexical_category'])}"
        for row in rows
    ) or "нет"
    return (
        "<b>🔇 Карточки без аудио</b>\n\n"
        f"Без US audio: {_number(stats['missing_us_audio'])}\n"
        f"Без UK audio: {_number(stats['missing_gb_audio'])}\n"
        f"Без обоих вариантов: {_number(stats['missing_audio'])}\n\n"
        f"<b>Первые {len(rows)} записей</b>\n{samples}"
    )


async def _render_health(database: Database, config: BotConfig, bot: Any) -> str:
    db_started = perf_counter()
    try:
        await database.ping()
        db_text = f"✅ {(perf_counter() - db_started) * 1000:.0f} ms"
    except Exception as exc:  # noqa: BLE001
        db_text = f"❌ {html.escape(str(exc)[:120])}"
    try:
        await bot.get_me()
        telegram_text = "✅"
    except Exception as exc:  # noqa: BLE001
        telegram_text = f"❌ {html.escape(str(exc)[:120])}"
    system = await database.admin_system_summary(
        since=datetime.now(timezone.utc) - timedelta(hours=24)
    )
    scheduler_text = {
        "completed": "✅",
        "running": "⏳",
        "failed": "❌",
        None: "⏳ ещё не запускался",
    }.get(system.get("scheduler_status"), "⚠️")
    last_job = system.get("scheduler_completed_at")
    last_job_text = (
        last_job.astimezone(config.timezone).strftime("%d.%m.%Y %H:%M:%S")
        if last_job
        else "—"
    )
    return (
        "<b>⚙️ System health</b>\n\n"
        "Bot: ✅\n"
        f"PostgreSQL: {db_text}\n"
        f"Scheduler: {scheduler_text}\n"
        f"Telegram API: {telegram_text}\n"
        f"Last delivery job: {last_job_text}\n\n"
        f"Errors in 24h: {_number(system['errors'])}"
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
            week_start=(local_now - timedelta(days=7)).astimezone(timezone.utc),
            month_start=(local_now - timedelta(days=30)).astimezone(timezone.utc),
        )
        levels = "\n".join(
            f"{level.upper()}: {_number(stats['levels'].get(level, 0))}"
            for level in ("a1", "a2", "b1", "b2", "c1", "c2")
        )
        dialects = ", ".join(
            f"{key.upper()}: {_number(value)}"
            for key, value in sorted(stats["dialects"].items())
        ) or "нет"
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
        await message.answer(
            f"<b>👤 User {user['telegram_user_id']}</b>\n\n"
            f"Username: {username}\n"
            f"Зарегистрирован: {registered:%d.%m.%Y %H:%M}\n"
            f"Уровни: {levels}\n"
            f"Произношение: {_dialect_label(user['pronunciation'])}\n"
            f"Карточек в день: {len(config.send_times)}\n"
            f"Время отправки: {', '.join(t.strftime('%H:%M') for t in config.send_times)}\n"
            f"Часовой пояс: {html.escape(config.timezone.key)}\n"
            f"Рассылка: {_delivery_state(user)}\n\n"
            f"Отправлено карточек: {_number(user['delivered_cards'])}\n"
            f"Последняя отправка: {last_text}\n"
            f"Ошибок доставки: {_number(user['failed_cards'])}"
        )

    async def send_word_details(message: Message, rows: tuple[dict[str, Any], ...]) -> None:
        if not rows:
            await message.answer("Слово не найдено.")
            return
        blocks = []
        for row in rows:
            word = row["word_us"] if row["word_us"] == row["word_gb"] else f"{row['word_us']} / {row['word_gb']}"
            blocks.append(
                f"<b>📖 {html.escape(word)}</b>\n"
                f"ID: {row['id']}\n"
                f"Part of speech: {html.escape(row['lexical_category'])}\n"
                f"CEFR: {str(row['cefr']).upper()}\n"
                f"IPA: {'✅' if row['ipa_us'] or row['ipa_gb'] else '❌'}\n"
                f"Definition: {'✅' if str(row['definition']).strip() else '❌'}\n"
                f"Example: {'✅' if str(row['example']).strip() else '❌'}\n"
                f"Translation: {'✅' if _translation_exists(row['translations']) else '❌'}\n"
                f"Audio: {'✅' if row.get('has_audio') else '❌'}\n"
                f"Telegram file_id: {'✅' if row.get('has_telegram_file_id') else '❌'}\n"
                f"Отправлено пользователям: {_number(row.get('delivered_count'))}\n"
                f"Статус: {'active' if row['is_active'] else 'disabled'}"
            )
        await message.answer("\n\n".join(blocks))

    @router.message(Command("word"))
    async def word_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return
        word = _arguments(message)
        if not word:
            await message.answer("Использование: <code>/word WORD</code>")
            return
        await send_word_details(message, await database.admin_word_search(word))

    @router.message(Command("word_id"))
    async def word_id_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return
        argument = _arguments(message)
        if not argument.isdigit():
            await message.answer("Использование: <code>/word_id ID</code>")
            return
        row = await database.admin_entry(int(argument))
        if not row:
            await message.answer("Словарная запись не найдена.")
            return
        await send_word_details(message, (row,))

    @router.message(Command("preview_word"))
    async def preview_word_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return
        parts = _arguments(message).lower().split()
        if not parts or not parts[0].isdigit() or (len(parts) > 1 and parts[1] not in {"us", "gb", "both"}):
            await message.answer("Использование: <code>/preview_word ID [us|gb|both]</code>")
            return
        card = await database.admin_preview_card(
            entry_id=int(parts[0]),
            dialect=parts[1] if len(parts) > 1 else None,
        )
        if not card:
            await message.answer("Запись не найдена или для выбранного произношения нет готового аудио.")
            return
        await delivery.send_preview(message.bot, chat_id=message.chat.id, card=card)

    @router.message(Command("send_test"))
    async def send_test_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return
        card = await database.admin_preview_card(random_card=True)
        if not card:
            await message.answer("Нет карточек с готовым аудио для тестовой отправки.")
            return
        await delivery.send_preview(message.bot, chat_id=message.chat.id, card=card)

    @router.message(Command("disable_word"))
    async def disable_word_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return
        argument = _arguments(message)
        if not argument.isdigit():
            await message.answer("Использование: <code>/disable_word ID</code>")
            return
        changed = await database.admin_set_entry_active(int(argument), False)
        await message.answer("Слово отключено." if changed else "Слово не найдено.")

    @router.message(Command("enable_word"))
    async def enable_word_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return
        argument = _arguments(message)
        if not argument.isdigit():
            await message.answer("Использование: <code>/enable_word ID</code>")
            return
        changed = await database.admin_set_entry_active(int(argument), True)
        await message.answer("Слово включено." if changed else "Слово не найдено.")

    @router.message(Command("retry_failed"))
    async def retry_failed_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return
        targets = await database.admin_retry_targets()
        if _arguments(message).lower() != "confirm":
            await message.answer(
                f"Готово к повторной отправке: {len(targets)}. "
                "Для запуска используйте <code>/retry_failed confirm</code>."
            )
            return
        delivered_count = failed_count = skipped_count = 0
        for target in targets:
            card = await database.admin_preview_card(
                entry_id=int(target["entry_id"]),
                dialect=str(target["dialect"]),
            )
            if not card:
                skipped_count += 1
                continue
            try:
                sent_message = await delivery.send_preview(
                    message.bot,
                    chat_id=int(target["chat_id"]),
                    card=card,
                )
                await database.finish_delivery(
                    int(target["id"]),
                    delivered=True,
                    telegram_message_id=sent_message.message_id,
                )
                delivered_count += 1
            except TelegramForbiddenError as exc:
                await database.deactivate_user(int(target["telegram_user_id"]))
                await database.finish_delivery(
                    int(target["id"]),
                    delivered=False,
                    error_type=classify_delivery_error(exc),
                    error_message=str(exc),
                )
                failed_count += 1
            except Exception as exc:  # noqa: BLE001
                await database.finish_delivery(
                    int(target["id"]),
                    delivered=False,
                    error_type=classify_delivery_error(exc),
                    error_message=str(exc),
                )
                failed_count += 1
        await message.answer(
            "Повторная отправка завершена.\n"
            f"Успешно: {delivered_count}\n"
            f"Ошибок: {failed_count}\n"
            f"Пропущено без готового аудио: {skipped_count}"
        )

    @router.message(Command("reload_templates"))
    async def reload_templates_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return
        try:
            delivery.reload_templates()
        except CardTemplateError as exc:
            await message.answer(f"Ошибка шаблона: <code>{html.escape(str(exc))}</code>")
            return
        await message.answer("Оба шаблона карточек проверены и перезагружены.")

    @router.message(Command("errors"))
    async def errors_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return
        since = datetime.now(timezone.utc) - timedelta(hours=24)
        system = await database.admin_system_summary(since=since)
        rows = await database.admin_failed_deliveries(start=since)
        lines = "\n".join(
            f"#{row['id']} · {ERROR_LABELS.get(row['error_type'] or 'unknown', row['error_type'] or 'Unknown')} · "
            f"{html.escape(str(row['error_message'])[:120])}"
            for row in rows
        ) or "нет"
        await message.answer(
            "<b>⚠️ Errors — 24h</b>\n"
            f"Всего: {_number(system['errors'])}\n\n"
            f"<b>Последние ошибки доставки</b>\n{lines}"
        )

    @router.message(Command("health"))
    async def health_handler(message: Message) -> None:
        if not await _is_admin(message, config):
            return
        db_started = perf_counter()
        try:
            await database.ping()
            db_text = f"✅ {(perf_counter() - db_started) * 1000:.0f} ms"
        except Exception as exc:  # noqa: BLE001
            db_text = f"❌ {html.escape(str(exc)[:120])}"
        try:
            await message.bot.get_me()
            telegram_text = "✅"
        except Exception as exc:  # noqa: BLE001
            telegram_text = f"❌ {html.escape(str(exc)[:120])}"
        system = await database.admin_system_summary(
            since=datetime.now(timezone.utc) - timedelta(hours=24)
        )
        scheduler_text = {
            "completed": "✅",
            "running": "⏳",
            "failed": "❌",
            None: "⏳ ещё не запускался",
        }.get(system.get("scheduler_status"), "⚠️")
        last_job = system.get("scheduler_completed_at")
        last_job_text = (
            last_job.astimezone(config.timezone).strftime("%d.%m.%Y %H:%M:%S")
            if last_job
            else "—"
        )
        await message.answer(
            "<b>⚙️ System health</b>\n\n"
            "Bot: ✅\n"
            f"PostgreSQL: {db_text}\n"
            f"Scheduler: {scheduler_text}\n"
            f"Telegram API: {telegram_text}\n"
            f"Last delivery job: {last_job_text}\n\n"
            f"Errors in 24h: {_number(system['errors'])}"
        )

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
            if action in "test_card":
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
            elif action == "errors_failed":
                text = await _render_failed(database, config)
                keyboard = admin_list_keyboard("errors")
            elif action == "audio_missing":
                text = await _render_missing_audio(database)
                keyboard = admin_list_keyboard("audio")
            elif action == "audio":
                text = await _render_audio(database)
                keyboard = admin_audio_keyboard()
            elif action == "errors":
                text = await _render_errors(database)
                keyboard = admin_errors_keyboard()
            elif action == "retry_info":
                targets = await database.admin_retry_targets()
                text = (
                    "<b>🔁 Повторная отправка</b>\n\n"
                    f"Готово к повтору: {len(targets)}\n\n"
                    "Чтобы избежать случайной массовой отправки, подтвердите её командой:\n"
                    "<code>/retry_failed confirm</code>"
                )
                keyboard = admin_errors_keyboard()
            elif action == "health":
                await callback.answer("Проверяю систему…")
                answered = True
                text = await _render_health(database, config, callback.bot)
                keyboard = admin_health_keyboard()
            elif action == "reload_templates":
                try:
                    delivery.reload_templates()
                    notice = "\n\n✅ Шаблоны проверены и перезагружены."
                except CardTemplateError as exc:
                    notice = f"\n\n❌ Ошибка шаблона: <code>{html.escape(str(exc))}</code>"
                text = await _render_health(database, config, callback.bot) + notice
                keyboard = admin_health_keyboard()
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
