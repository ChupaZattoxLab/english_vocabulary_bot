"""Bot runtime table definitions."""

from tgbot.db.tables.bot.scheduler_runs import BotSchedulerRun, bot_scheduler_runs
from tgbot.db.tables.bot.telegram_audio_cache import (
    BotTelegramAudioCache,
    bot_telegram_audio_cache,
)
from tgbot.db.tables.bot.user_cards import BotUserCard, bot_user_cards
from tgbot.db.tables.bot.users import BotUser, bot_users

__all__ = [
    "BotSchedulerRun",
    "BotTelegramAudioCache",
    "BotUser",
    "BotUserCard",
    "bot_scheduler_runs",
    "bot_telegram_audio_cache",
    "bot_user_cards",
    "bot_users",
]
