"""Shared helpers for Telegram handlers (handlers/ only)."""

from __future__ import annotations

from aiogram.types import CallbackQuery, Message


def callback_message(callback: CallbackQuery) -> Message | None:
    message = callback.message
    return message if isinstance(message, Message) else None


def command_arguments(message: Message) -> str:
    text = message.text or ""
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else ""


def format_number(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def format_levels(levels: tuple[str, ...], empty: str) -> str:
    return ", ".join(level.upper() for level in levels) or empty
