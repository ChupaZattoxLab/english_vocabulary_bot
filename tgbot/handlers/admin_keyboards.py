"""Inline navigation keyboards for the administrator panel."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from tgbot.localization import locale


def admin_main_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    buttons = (
        (locale.keyboard.admin_users, "admin:users"),
        (locale.keyboard.admin_test_card, "admin:test_card"),
        (locale.keyboard.admin_refresh, "admin:overview"),
    )
    for text, callback_data in buttons:
        builder.button(text=text, callback_data=callback_data)
    builder.adjust(2, 1)
    return builder.as_markup()


def admin_users_keyboard() -> InlineKeyboardMarkup:
    return _back_and_refresh("users")


def word_categories_keyboard(
    rows: Sequence[Mapping[str, object]],
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    category_counts: dict[str, int] = {}
    for row in rows:
        category = (
            str(row["lexical_category"]).strip() or locale.keyboard.unknown_category
        )
        category_counts[category] = category_counts.get(category, 0) + 1

    for row in rows:
        entry_id = int(row["id"])
        category = (
            str(row["lexical_category"]).strip() or locale.keyboard.unknown_category
        )
        text = category
        if category_counts[category] > 1:
            cefr = str(row.get("cefr") or "").upper()
            text = f"{category} · {cefr or locale.keyboard.dash} · #{entry_id}"
        builder.button(text=text, callback_data=f"admin:word:{entry_id}")
    builder.adjust(2)
    return builder.as_markup()


def _back_and_refresh(section: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.button(text=locale.keyboard.admin_back, callback_data="admin:overview")
    builder.button(
        text=locale.keyboard.admin_refresh,
        callback_data=f"admin:{section}",
    )
    builder.adjust(2)
    return builder.as_markup()
