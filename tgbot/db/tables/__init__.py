"""SQLAlchemy declarative table definitions for PostgreSQL.

Shared by the async bot runtime (SQLAlchemy Core via ``Model.__table__``)
and Alembic migrations.
"""

from tgbot.db.tables.base import Base, metadata
from tgbot.db.tables.bot import (
    BotSchedulerRun,
    BotTelegramAudioCache,
    BotUser,
    BotUserCard,
    bot_scheduler_runs,
    bot_telegram_audio_cache,
    bot_user_cards,
    bot_users,
)
from tgbot.db.tables.oald import (
    OaldAudioFile,
    OaldAudioVariant,
    OaldEntry,
    OaldEntryAudioSource,
    OxfordLexicalEntry,
    oald_audio_files,
    oald_audio_variants,
    oald_entries,
    oald_entry_audio_sources,
    oxford_lexical_entries,
)

MANAGED_TABLES = frozenset(metadata.tables)

__all__ = [
    "Base",
    "BotSchedulerRun",
    "BotTelegramAudioCache",
    "BotUser",
    "BotUserCard",
    "MANAGED_TABLES",
    "OaldAudioFile",
    "OaldAudioVariant",
    "OaldEntry",
    "OaldEntryAudioSource",
    "OxfordLexicalEntry",
    "bot_scheduler_runs",
    "bot_telegram_audio_cache",
    "bot_user_cards",
    "bot_users",
    "metadata",
    "oald_audio_files",
    "oald_audio_variants",
    "oald_entries",
    "oald_entry_audio_sources",
    "oxford_lexical_entries",
]
