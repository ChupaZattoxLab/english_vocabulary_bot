"""Domain models returned by database queries."""

from tgbot.db.models.audience_stats import AudienceStats
from tgbot.db.models.card import Card, CardAudio, DialectVariant, card_from_row
from tgbot.db.models.types import (
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
from tgbot.db.models.user import (
    ActiveUser,
    AdminUser,
    CardDeliveryPrefs,
    User,
    UserSettings,
    active_user_from_row,
    admin_user_from_row,
    card_delivery_prefs_from_row,
)
from tgbot.db.models.word_match import WordMatch, word_match_from_row

__all__ = [
    "ActiveUser",
    "AdminUser",
    "AudienceStats",
    "AudioConversionStatus",
    "AudioDownloadStatus",
    "AudioVariantType",
    "Card",
    "CardAudio",
    "CardDeliveryPrefs",
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
    "WordMatch",
    "active_user_from_row",
    "admin_user_from_row",
    "card_delivery_prefs_from_row",
    "card_from_row",
    "word_match_from_row",
]
