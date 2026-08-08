"""Bot runtime table definitions."""

from tgbot.db.schema.bot.scheduler_runs import bot_scheduler_runs
from tgbot.db.schema.bot.telegram_audio_cache import bot_telegram_audio_cache
from tgbot.db.schema.bot.user_cards import bot_user_cards
from tgbot.db.schema.bot.users import bot_users

__all__ = [
    "bot_scheduler_runs",
    "bot_telegram_audio_cache",
    "bot_user_cards",
    "bot_users",
]
