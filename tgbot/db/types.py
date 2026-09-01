"""Database package types, enums, and query-layer constants (db/ only)."""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class Dialect(StrEnum):
    US = "us"
    GB = "gb"


class DialectPreference(StrEnum):
    US = "us"
    GB = "gb"
    BOTH = "both"


class CefrLevel(StrEnum):
    A1 = "a1"
    A2 = "a2"
    B1 = "b1"
    B2 = "b2"
    C1 = "c1"


class UserRole(StrEnum):
    USER = "user"
    ADMIN = "admin"


class CardStatus(StrEnum):
    RESERVED = "reserved"
    DELIVERED = "delivered"
    FAILED = "failed"


class SchedulerRunStatus(StrEnum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AudioDownloadStatus(StrEnum):
    PENDING = "pending"
    DOWNLOADED = "downloaded"
    FAILED = "failed"


class AudioConversionStatus(StrEnum):
    PENDING = "pending"
    PREPARED = "prepared"
    FAILED = "failed"


class AudioVariantType(StrEnum):
    TELEGRAM_VOICE_OPUS = "telegram_voice_opus"


class TelegramSendMethod(StrEnum):
    VOICE = "voice"
    AUDIO = "audio"
    DOCUMENT = "document"


VALID_LEVELS: Final[tuple[CefrLevel, ...]] = tuple(CefrLevel)
VALID_DIALECTS: Final[tuple[Dialect, ...]] = tuple(Dialect)
VALID_DIALECT_PREFERENCES: Final[tuple[DialectPreference, ...]] = tuple(
    DialectPreference
)
VALID_ROLES: Final[tuple[UserRole, ...]] = tuple(UserRole)

# Connection pool (Database / sync helpers).
DB_CONNECT_TIMEOUT_SECONDS = 10
DB_POOL_RECYCLE_SECONDS = 1800

# Statuses that still occupy the per-user entry/slot unique indexes.
CARD_OCCUPIED_STATUSES = (CardStatus.DELIVERED, CardStatus.RESERVED)

# Reservation reclaim + scheduler claim windows
CARD_RESERVATION_TIMEOUT_MINUTES = 15
SCHEDULER_RETRY_COOLDOWN_MINUTES = 2
SCHEDULER_STALE_RUNNING_MINUTES = 15

# bot_user_cards.error_type / error_message
ERROR_TYPE_STALE_RESERVATION = "stale_reservation"
ERROR_TYPE_MAX_LEN = 100
ERROR_MESSAGE_MAX_LEN = 2000
