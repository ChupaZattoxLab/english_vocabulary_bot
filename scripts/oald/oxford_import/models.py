"""Domain models for Oxford cache import."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class OxfordCacheError(ValueError):
    """Raised when a cache file cannot be parsed in strict mode."""


class OxfordDatabaseError(RuntimeError):
    """Raised when PostgreSQL setup or import fails."""


@dataclass(frozen=True)
class DatasetDefinition:
    ordinal: int
    word: str
    part_of_speech: str
    phonetic: str
    definition: str
    example: str


@dataclass
class OxfordGroup:
    source_lexical_key: str
    lexical_category: str
    base_words: list[str] = field(default_factory=list)
    us_variants: list[str] = field(default_factory=list)
    gb_variants: list[str] = field(default_factory=list)
    pronunciations_us: list[tuple[str, str]] = field(default_factory=list)
    pronunciations_gb: list[tuple[str, str]] = field(default_factory=list)
    translations: list[str] = field(default_factory=list)
    entry_count: int = 0


@dataclass(frozen=True)
class OxfordRow:
    source_lexical_key: str
    word_us: str
    word_gb: str
    lexical_category: str
    ipa_us: list[str]
    ipa_gb: list[str]
    definition: str
    example: str
    audio_source_us: list[str]
    audio_source_gb: list[str]
    translations: list[str]

    def as_parameters(self) -> dict[str, Any]:
        return {
            "source_lexical_key": self.source_lexical_key,
            "word_us": self.word_us,
            "word_gb": self.word_gb,
            "lexical_category": self.lexical_category,
            "ipa_us": self.ipa_us,
            "ipa_gb": self.ipa_gb,
            "definition": self.definition,
            "example": self.example,
            "audio_source_us": self.audio_source_us,
            "audio_source_gb": self.audio_source_gb,
            "translations": self.translations,
        }
