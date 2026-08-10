"""Shared type aliases and model constants."""

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
