"""Administrator panel navigation keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from tgbot.localization import locale


def admin_main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for text, callback_data in (
        (locale.keyboard.admin_users, "admin:users"),
        (locale.keyboard.admin_refresh, "admin:refresh"),
    ):
        builder.button(text=text, callback_data=callback_data)
    builder.adjust(2)
    return builder.as_markup()


def admin_section_keyboard(section: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=locale.keyboard.admin_back, callback_data="admin:refresh")
    builder.button(
        text=locale.keyboard.admin_refresh,
        callback_data=f"admin:{section}",
    )
    builder.adjust(2)
    return builder.as_markup()
