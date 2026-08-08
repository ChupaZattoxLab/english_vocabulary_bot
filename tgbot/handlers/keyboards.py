"""Inline keyboards for CEFR and pronunciation selection."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from tgbot.db.models import VALID_LEVELS

LEVELS = tuple(level.upper() for level in VALID_LEVELS)


def levels_keyboard(selected_levels: tuple[str, ...]) -> InlineKeyboardMarkup:
    selected = {level.lower() for level in selected_levels}
    rows: list[list[InlineKeyboardButton]] = []
    for start in range(0, len(LEVELS), 3):
        row: list[InlineKeyboardButton] = []
        for level in LEVELS[start : start + 3]:
            marker = "✅ " if level.lower() in selected else ""
            row.append(
                InlineKeyboardButton(
                    text=f"{marker}{level}",
                    callback_data=f"level:{level.lower()}",
                )
            )
        rows.append(row)
    rows.append([InlineKeyboardButton(text="Продолжить", callback_data="level:done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pronunciation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🇺🇸 American (US)",
                    callback_data="dialect:us",
                ),
                InlineKeyboardButton(
                    text="🇬🇧 British (GB)",
                    callback_data="dialect:gb",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🇺🇸 + 🇬🇧 Оба варианта",
                    callback_data="dialect:both",
                )
            ],
        ]
    )
