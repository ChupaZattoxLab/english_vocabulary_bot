"""Telegram command and callback handlers."""

from tgbot.handlers.admin import create_admin_router
from tgbot.handlers.user import create_router

__all__ = [
    "create_admin_router",
    "create_router",
]
