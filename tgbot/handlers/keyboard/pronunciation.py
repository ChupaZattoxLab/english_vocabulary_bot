"""Pronunciation / dialect preference keyboard."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from tgbot.localization import locale


def pronunciation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=locale.keyboard.pronunciation_us,
                    callback_data="dialect:us",
                ),
                InlineKeyboardButton(
                    text=locale.keyboard.pronunciation_gb,
                    callback_data="dialect:gb",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=locale.keyboard.pronunciation_both,
                    callback_data="dialect:both",
                )
            ],
        ]
    )
