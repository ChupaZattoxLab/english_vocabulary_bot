"""Word match category picker for /word."""

from __future__ import annotations

from collections.abc import Sequence

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from tgbot.db.models import Card


def word_categories_keyboard(rows: Sequence[Card]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    category_counts: dict[str, int] = {}
    for row in rows:
        category_counts[row.lexical_category] = (
            category_counts.get(row.lexical_category, 0) + 1
        )

    for row in rows:
        category = row.lexical_category
        text = (
            f"{category} · {row.cefr.upper()} · #{row.entry_id}"
            if category_counts[category] > 1
            else category
        )
        builder.button(text=text, callback_data=f"admin:word:{row.entry_id}")

    builder.adjust(2)
    return builder.as_markup()
