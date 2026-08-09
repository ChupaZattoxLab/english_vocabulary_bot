"""PostgreSQL access and schema metadata for the bot."""

from tgbot.db.database import Database
from tgbot.db.domain import (
    ActiveUser,
    AdminContentSummary,
    AdminUserDetail,
    AdminUsersSummary,
    AdminWordMatch,
    BotUser,
    DatabaseError,
    ReservedAudio,
    ReservedCard,
)

__all__ = [
    "ActiveUser",
    "AdminContentSummary",
    "AdminUserDetail",
    "AdminUsersSummary",
    "AdminWordMatch",
    "BotUser",
    "Database",
    "DatabaseError",
    "ReservedAudio",
    "ReservedCard",
]
