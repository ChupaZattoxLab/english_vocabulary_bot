"""Canonical SQLAlchemy metadata for the PostgreSQL schema.

Shared by the async bot runtime (SQLAlchemy Core) and Alembic migrations.
"""

from tgbot.db.schema.base import metadata
from tgbot.db.schema.bot import (
    bot_scheduler_runs,
    bot_telegram_audio_cache,
    bot_user_cards,
    bot_users,
)
from tgbot.db.schema.oald import (
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
