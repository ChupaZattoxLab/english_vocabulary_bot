"""Vocabulary card models for delivery."""

from __future__ import annotations

from dataclasses import dataclass

from tgbot.models.types import Dialect


@dataclass(frozen=True)
class CardAudio:
    source_url: str
    audio_data: bytes
    content_type: str
    filename: str


@dataclass(frozen=True)
class DialectVariant:
    dialect: Dialect
    word: str
    ipa: str
    audio: CardAudio


@dataclass(frozen=True)
class Card:
    history_id: int
    entry_id: int
    lexical_category: str
    cefr: str
    definition: str
    example: str
    translation: str
    us: DialectVariant | None
    gb: DialectVariant | None

    @property
    def is_both(self) -> bool:
        return self.us is not None and self.gb is not None

    @property
    def primary(self) -> DialectVariant:
        if self.us is not None:
            return self.us
        if self.gb is not None:
            return self.gb
        raise ValueError("card has no dialect variants")

    def variants(self) -> tuple[DialectVariant, ...]:
        return tuple(variant for variant in (self.us, self.gb) if variant is not None)
