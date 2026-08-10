"""Vocabulary card models for delivery."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, cast

from tgbot.db.models.types import Dialect, DialectPreference


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
    user_card_id: int
    entry_id: int
    word_us: str
    word_gb: str
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

    def for_preference(self, preference: DialectPreference) -> Card:
        """Return a view of this card for a user dialect preference."""
        us = self.us if preference in {"us", "both"} else None
        gb = self.gb if preference in {"gb", "both"} else None

        if preference in {"us", "both"} and us is None:
            raise ValueError("card has no US variant")
        if preference in {"gb", "both"} and gb is None:
            raise ValueError("card has no GB variant")

        return replace(self, us=us, gb=gb)


def card_from_row(
    row: object,
    *,
    preference: DialectPreference = "both",
    user_card_id: int = 0,
) -> Card:
    """Build a Card from an oald entry + audio mapping row.

    ``word_us`` / ``word_gb`` always come from the entry (may be identical).
    ``preference`` only controls which dialect audio variants are attached.
    """
    data = dict(cast(Mapping[Any, Any], row))
    word_us = str(data["word_us"])
    word_gb = str(data["word_gb"])
    include_us = preference in {"us", "both"}
    include_gb = preference in {"gb", "both"}

    return Card(
        user_card_id=user_card_id,
        entry_id=int(data["entry_id"]),
        word_us=word_us,
        word_gb=word_gb,
        lexical_category=str(data["lexical_category"]),
        cefr=str(data["cefr"]).upper(),
        definition=str(data.get("definition") or ""),
        example=str(data.get("example") or ""),
        translation=russian_translation(data.get("translations")),
        us=(
            DialectVariant(
                dialect="us",
                word=word_us,
                ipa=ipa_at_position(
                    data.get("ipa_us") or (),
                    data.get("us_source_position"),
                ),
                audio=card_audio_from_row(data, prefix="us"),
            )
            if include_us
            else None
        ),
        gb=(
            DialectVariant(
                dialect="gb",
                word=word_gb,
                ipa=ipa_at_position(
                    data.get("ipa_gb") or (),
                    data.get("gb_source_position"),
                ),
                audio=card_audio_from_row(data, prefix="gb"),
            )
            if include_gb
            else None
        ),
    )


def card_audio_from_row(data: Mapping[Any, Any], *, prefix: str) -> CardAudio:
    raw = data.get(f"{prefix}_audio_data") or b""
    if isinstance(raw, memoryview):
        audio_data = raw.tobytes()
    else:
        audio_data = bytes(raw)

    return CardAudio(
        source_url=str(data.get(f"{prefix}_source_url") or ""),
        audio_data=audio_data,
        content_type=str(data.get(f"{prefix}_content_type") or ""),
        filename=str(data.get(f"{prefix}_filename") or ""),
    )


def ipa_at_position(values: object, position: object) -> str:
    """Pick IPA matching the chosen audio source_position; else first / empty."""
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
        return ""
    items = [str(item) for item in values]
    if not items:
        return ""
    if isinstance(position, int) and 0 <= position < len(items):
        return items[position]
    return items[0]


def russian_translation(translations: object) -> str:
    """Flatten translations.ru.main + also into a comma-separated string."""
    source = translations if isinstance(translations, Mapping) else {}
    russian_raw = source.get("ru")
    russian = russian_raw if isinstance(russian_raw, Mapping) else {}

    values = [str(russian.get("main") or "").strip()]
    also = russian.get("also") or []

    if isinstance(also, Sequence) and not isinstance(also, (str, bytes)):
        values.extend(str(value).strip() for value in also)

    return ", ".join(value for value in dict.fromkeys(values) if value)
