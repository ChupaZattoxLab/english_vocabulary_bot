"""SQLAlchemy ``Table`` definitions for PostgreSQL.

Shared by the async bot runtime (SQLAlchemy Core) and Alembic migrations.
"""

from tgbot.db.tables.base import metadata
from tgbot.db.tables.bot import (
    bot_scheduler_runs,
    bot_telegram_audio_cache,
    bot_user_cards,
    bot_users,
)
from tgbot.db.tables.oald import (
    oald_audio_files,
    oald_audio_variants,
    oald_entries,
    oald_entry_audio_sources,
    oxford_lexical_entries,
)

MANAGED_TABLES = frozenset(metadata.tables)

__all__ = [
    "MANAGED_TABLES",
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
