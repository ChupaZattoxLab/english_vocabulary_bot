"""Reserved vocabulary card models for delivery."""

from __future__ import annotations

from dataclasses import dataclass

from tgbot.db.domain.types import CardDialect


@dataclass(frozen=True)
class ReservedAudio:
    dialect: CardDialect
    source_url: str
    audio_data: bytes
    content_type: str
    filename: str


@dataclass(frozen=True)
class ReservedCard:
    history_id: int
    entry_id: int
    word: str
    lexical_category: str
    cefr: str
    definition: str
    example: str
    ipa: str
    dialect: CardDialect
    translation: str
    source_url: str
    audio_data: bytes
    content_type: str
    filename: str
    word_us: str = ""
    word_gb: str = ""
    ipa_us: str = ""
    ipa_gb: str = ""
    secondary_audio: ReservedAudio | None = None
