"""Shared display labels for pronunciation and dialects."""

from __future__ import annotations

PRONUNCIATION_SHORT = {
    "us": "US",
    "gb": "GB",
    "both": "US + GB",
}

PRONUNCIATION_ADMIN = {
    "us": "American English",
    "gb": "British English",
    "both": "American + British English",
}

DIALECT_FLAGS = {
    "US": "🇺🇸",
    "GB": "🇬🇧",
    "BOTH": "🇺🇸 + 🇬🇧",
}

DIALECT_CAPTIONS = {
    "US": "🇺🇸 US",
    "GB": "🇬🇧 GB",
}


def pronunciation_short(value: str | None) -> str:
    return PRONUNCIATION_SHORT.get(value or "", "не выбрано")


def pronunciation_admin(value: str | None) -> str:
    return PRONUNCIATION_ADMIN.get(value or "", "не выбран")


def dialect_flag(dialect: str) -> str:
    return DIALECT_FLAGS.get(dialect.upper(), "")


def dialect_caption(dialect: str) -> str:
    normalized = dialect.upper()
    return DIALECT_CAPTIONS.get(normalized, normalized)
