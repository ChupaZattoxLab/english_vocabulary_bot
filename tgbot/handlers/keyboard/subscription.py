"""Channel subscription prompt keyboard."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from tgbot.localization import locale
from tgbot.types import CHANNEL_URL


def subscription_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=locale.keyboard.subscribe, url=CHANNEL_URL)],
            [
                InlineKeyboardButton(
                    text=locale.keyboard.subscribed,
                    callback_data="subscription:check",
                )
            ],
        ]
    )
