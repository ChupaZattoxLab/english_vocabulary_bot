"""Inline keyboards for user onboarding and the admin panel."""

from tgbot.handlers.keyboard.admin import admin_main_keyboard, admin_section_keyboard
from tgbot.handlers.keyboard.levels import levels_keyboard
from tgbot.handlers.keyboard.pronunciation import pronunciation_keyboard
from tgbot.handlers.keyboard.settings import (
    settings_keyboard,
    settings_levels_keyboard,
    settings_pronunciation_keyboard,
)
from tgbot.handlers.keyboard.words import word_categories_keyboard

__all__ = [
    "admin_main_keyboard",
    "admin_section_keyboard",
    "levels_keyboard",
    "pronunciation_keyboard",
    "settings_keyboard",
    "settings_levels_keyboard",
    "settings_pronunciation_keyboard",
    "word_categories_keyboard",
]
