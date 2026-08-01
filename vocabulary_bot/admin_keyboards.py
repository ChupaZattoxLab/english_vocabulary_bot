"""Inline navigation keyboards for the administrator panel."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    buttons = (
        ("👥 Пользователи", "admin:users"),
        ("📨 Рассылки", "admin:delivery"),
        ("📚 Контент", "admin:content"),
        ("🔊 Аудио", "admin:audio"),
        ("⚠️ Ошибки", "admin:errors"),
        ("🧪 Тест-карта", "admin:test_card"),
        ("⚙️ Система", "admin:health"),
        ("🔄 Обновить", "admin:overview"),
    )
    for text, callback_data in buttons:
        builder.button(text=text, callback_data=callback_data)
    builder.adjust(2, 2, 2, 2)
    return builder.as_markup()


def admin_users_keyboard() -> InlineKeyboardMarkup:
    return _back_and_refresh("users")


def admin_delivery_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Сегодня", callback_data="admin:delivery_today")
    builder.button(text="7️⃣ За 7 дней", callback_data="admin:delivery_7d")
    builder.button(text="❌ Неуспешные", callback_data="admin:delivery_failed")
    builder.button(text="⬅️ Назад", callback_data="admin:overview")
    builder.button(text="🔄 Обновить", callback_data="admin:delivery")
    builder.adjust(2, 1, 2)
    return builder.as_markup()


def admin_content_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔍 Проблемные карточки", callback_data="admin:missing_fields")
    builder.button(text="🔊 Без аудио", callback_data="admin:missing_audio")
    builder.button(text="🏷 Без CEFR", callback_data="admin:missing_cefr")
    builder.button(text="👁 Случайный preview", callback_data="admin:preview_card")
    builder.button(text="⬅️ Назад", callback_data="admin:overview")
    builder.button(text="🔄 Обновить", callback_data="admin:content")
    builder.adjust(1, 2, 1, 2)
    return builder.as_markup()


def admin_audio_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🔊 Без аудио", callback_data="admin:audio_missing")
    builder.button(text="⬅️ Назад", callback_data="admin:overview")
    builder.button(text="🔄 Обновить", callback_data="admin:audio")
    builder.adjust(1, 2)
    return builder.as_markup()


def admin_errors_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Ошибки доставки", callback_data="admin:errors_failed")
    builder.button(text="🔁 Повторить ошибки", callback_data="admin:retry_info")
    builder.button(text="⬅️ Назад", callback_data="admin:overview")
    builder.button(text="🔄 Обновить", callback_data="admin:errors")
    builder.adjust(1, 1, 2)
    return builder.as_markup()


def admin_health_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="🧩 Перезагрузить шаблоны", callback_data="admin:reload_templates")
    builder.button(text="⬅️ Назад", callback_data="admin:overview")
    builder.button(text="🔄 Обновить", callback_data="admin:health")
    builder.adjust(1, 2)
    return builder.as_markup()


def admin_list_keyboard(back_to: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад", callback_data=f"admin:{back_to}")
    builder.button(text="🏠 Обзор", callback_data="admin:overview")
    builder.adjust(2)
    return builder.as_markup()


def _back_and_refresh(section: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text="⬅️ Назад", callback_data="admin:overview")
    builder.button(text="🔄 Обновить", callback_data=f"admin:{section}")
    builder.adjust(2)
    return builder.as_markup()
