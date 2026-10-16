"""CEFR level selection keyboard."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from tgbot.db.models import VALID_LEVELS
from tgbot.localization import locale

LEVELS = tuple(level.upper() for level in VALID_LEVELS)


def levels_keyboard(selected_levels: tuple[str, ...]) -> InlineKeyboardMarkup:
    selected = {level.lower() for level in selected_levels}
    rows: list[list[InlineKeyboardButton]] = []

    for start in range(0, len(LEVELS), 3):
        row = [
            InlineKeyboardButton(
                text=(
                    f"{locale.keyboard.level_selected_prefix}{level}"
                    if level.lower() in selected
                    else level
                ),
                callback_data=f"level:{level.lower()}",
            )
            for level in LEVELS[start : start + 3]
        ]
        rows.append(row)

    rows.append(
        [
            InlineKeyboardButton(
                text=locale.keyboard.continue_button,
                callback_data="level:done",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
