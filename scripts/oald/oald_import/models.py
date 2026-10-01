"""Domain models for OALD JSON import."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from tgbot.db.models import CefrLevel, Dialect


class OaldValidationError(ValueError):
    """Raised when OALD JSON does not match the expected schema."""


class OaldDatabaseError(RuntimeError):
    """Raised when the OALD PostgreSQL setup or import fails."""


@dataclass(frozen=True)
class OaldEntry:
    word_us: str
    word_gb: str
    lexical_category: str
    cefr: CefrLevel
    definition_url_oxford: str
    definition_url_cambridge: str
    ipa_us: list[str]
    ipa_gb: list[str]
    definition: str
    example: str
    audio_source_us: list[str]
    audio_source_gb: list[str]
    translations: dict[str, Any]

    def values(self) -> dict[str, Any]:
        return {
            "word_us": self.word_us,
            "word_gb": self.word_gb,
            "lexical_category": self.lexical_category,
            "cefr": self.cefr,
            "definition_url_oxford": self.definition_url_oxford,
            "definition_url_cambridge": self.definition_url_cambridge,
            "ipa_us": self.ipa_us,
            "ipa_gb": self.ipa_gb,
            "definition": self.definition,
            "example": self.example,
            "audio_source_us": self.audio_source_us,
            "audio_source_gb": self.audio_source_gb,
            "translations": self.translations,
        }

    def audio_references(self) -> Iterator[tuple[Dialect, int, str]]:
        for dialect, urls in (
            (Dialect.US, self.audio_source_us),
            (Dialect.GB, self.audio_source_gb),
        ):
            for position, source_url in enumerate(urls):
                yield dialect, position, source_url


@dataclass(frozen=True)
class ImportResult:
    entries: int
    audio_references: int
    unique_audio_urls: int
