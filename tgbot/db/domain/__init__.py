"""Domain dataclasses returned by bot database queries."""

from tgbot.db.domain.admin import (
    AdminContentSummary,
    AdminUserDetail,
    AdminUsersSummary,
    AdminWordMatch,
)
from tgbot.db.domain.cards import ReservedAudio, ReservedCard
from tgbot.db.domain.types import (
    VALID_LEVELS,
    VALID_PRONUNCIATIONS,
    CardDialect,
    CefrLevel,
    DatabaseError,
    DbRow,
    Pronunciation,
)
from tgbot.db.domain.users import ActiveUser, BotUser

__all__ = [
    "ActiveUser",
    "AdminContentSummary",
    "AdminUserDetail",
    "AdminUsersSummary",
    "AdminWordMatch",
    "BotUser",
    "CardDialect",
    "CefrLevel",
    "DatabaseError",
    "DbRow",
    "Pronunciation",
    "ReservedAudio",
    "ReservedCard",
    "VALID_LEVELS",
    "VALID_PRONUNCIATIONS",
]
