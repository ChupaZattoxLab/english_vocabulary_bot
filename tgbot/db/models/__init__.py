"""Domain models returned by database queries."""

from tgbot.db.models.audience_stats import AudienceStats
from tgbot.db.models.card import Card, CardAudio, EnglishVarietyVariant, card_from_row
from tgbot.db.models.user import (
    AdminUser,
    User,
    UserSettings,
    admin_user_from_row,
    user_from_row,
)
from tgbot.db.types import (
    VALID_ENGLISH_VARIETIES,
    VALID_ENGLISH_VARIETY_PREFERENCES,
    VALID_LEVELS,
    VALID_ROLES,
    AudioConversionStatus,
    AudioDownloadStatus,
    CardStatus,
    CefrLevel,
    EnglishVariety,
    EnglishVarietyPreference,
    SchedulerRunStatus,
    UserRole,
)

__all__ = [
    "User",
    "AdminUser",
    "AudienceStats",
    "AudioConversionStatus",
    "AudioDownloadStatus",
    "Card",
    "CardAudio",
    "CardStatus",
    "CefrLevel",
    "EnglishVariety",
    "EnglishVarietyPreference",
    "EnglishVarietyVariant",
    "SchedulerRunStatus",
    "User",
    "UserRole",
    "UserSettings",
    "VALID_ENGLISH_VARIETY_PREFERENCES",
    "VALID_ENGLISH_VARIETIES",
    "VALID_LEVELS",
    "VALID_ROLES",
    "user_from_row",
    "admin_user_from_row",
    "card_from_row",
]
