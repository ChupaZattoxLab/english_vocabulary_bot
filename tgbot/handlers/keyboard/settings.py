"""Settings menu and draft selection keyboards."""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from tgbot.db.models import VALID_LEVELS
from tgbot.handlers.keyboard.levels import levels_keyboard
from tgbot.handlers.keyboard.pronunciation import pronunciation_keyboard
from tgbot.localization import locale


def settings_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=locale.keyboard.settings_levels,
                    callback_data="settings:open_levels",
                ),
                InlineKeyboardButton(
                    text=locale.keyboard.settings_pronunciation,
                    callback_data="settings:open_pronunciation",
                ),
            ]
        ]
    )


def settings_actions(callback_data: str) -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            text=locale.keyboard.confirm_button, callback_data=callback_data
        ),
        InlineKeyboardButton(
            text=locale.keyboard.back_button, callback_data="settings:back"
        ),
    ]


def settings_levels_keyboard(selected_levels: tuple[str, ...]) -> InlineKeyboardMarkup:
    markup = levels_keyboard(selected_levels)
    for row in markup.inline_keyboard[:-1]:
        for button in row:
            level = (button.callback_data or "").removeprefix("level:")
            selected = set(selected_levels) ^ {level}
            draft = ",".join(value for value in VALID_LEVELS if value in selected)
            button.callback_data = f"settings:levels:{draft}"
    markup.inline_keyboard[-1] = settings_actions(
        f"settings:save_levels:{','.join(selected_levels)}"
    )
    return markup


def settings_pronunciation_keyboard(selected: str | None) -> InlineKeyboardMarkup:
    markup = pronunciation_keyboard()
    for row in markup.inline_keyboard:
        for button in row:
            value = (button.callback_data or "").split(":", 1)[-1]
            button.callback_data = f"settings:pronunciation:{value}"
            if value == selected:
                button.text = locale.keyboard.level_selected_prefix + button.text
    markup.inline_keyboard.append(
        settings_actions(f"settings:save_pronunciation:{selected or ''}")
    )
    return markup
