"""Domain models returned by database queries."""

from tgbot.db.models.audience_stats import AudienceStats
from tgbot.db.models.card import Card, CardAudio, DialectVariant, card_from_row
from tgbot.db.models.user import (
    AdminUser,
    User,
    UserSettings,
    admin_user_from_row,
    user_from_row,
)
from tgbot.db.types import (
    VALID_DIALECT_PREFERENCES,
    VALID_DIALECTS,
    VALID_LEVELS,
    VALID_ROLES,
    AudioConversionStatus,
    AudioDownloadStatus,
    AudioVariantType,
    CardStatus,
    CefrLevel,
    Dialect,
    DialectPreference,
    SchedulerRunStatus,
    TelegramSendMethod,
    UserRole,
)

__all__ = [
    "User",
    "AdminUser",
    "AudienceStats",
    "AudioConversionStatus",
    "AudioDownloadStatus",
    "AudioVariantType",
    "Card",
    "CardAudio",
    "CardStatus",
    "CefrLevel",
    "Dialect",
    "DialectPreference",
    "DialectVariant",
    "SchedulerRunStatus",
    "TelegramSendMethod",
    "User",
    "UserRole",
    "UserSettings",
    "VALID_DIALECT_PREFERENCES",
    "VALID_DIALECTS",
    "VALID_LEVELS",
    "VALID_ROLES",
    "user_from_row",
    "admin_user_from_row",
    "card_from_row",
]
