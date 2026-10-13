"""Vocabulary card models for delivery."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, cast

from tgbot.db.types import EnglishVariety, EnglishVarietyPreference


@dataclass(frozen=True)
class CardAudio:
    source_url: str
    audio_data: bytes
    content_type: str
    filename: str


@dataclass(frozen=True)
class EnglishVarietyVariant:
    english_variety: EnglishVariety
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
    us: EnglishVarietyVariant | None
    gb: EnglishVarietyVariant | None

    @property
    def is_both(self) -> bool:
        return self.us is not None and self.gb is not None

    @property
    def primary(self) -> EnglishVarietyVariant:
        if self.us is not None:
            return self.us
        if self.gb is not None:
            return self.gb
        raise ValueError("card has no English variety variants")

    def variants(self) -> tuple[EnglishVarietyVariant, ...]:
        return tuple(variant for variant in (self.us, self.gb) if variant is not None)

    def for_preference(self, preference: EnglishVarietyPreference) -> Card:
        """Return a view of this card for a user's English variety preference."""
        us = (
            self.us
            if preference
            in {EnglishVarietyPreference.US, EnglishVarietyPreference.BOTH}
            else None
        )
        gb = (
            self.gb
            if preference
            in {EnglishVarietyPreference.GB, EnglishVarietyPreference.BOTH}
            else None
        )

        if (
            preference in {EnglishVarietyPreference.US, EnglishVarietyPreference.BOTH}
            and us is None
        ):
            raise ValueError("card has no US variant")
        if (
            preference in {EnglishVarietyPreference.GB, EnglishVarietyPreference.BOTH}
            and gb is None
        ):
            raise ValueError("card has no GB variant")

        return replace(self, us=us, gb=gb)


def card_from_row(
    row: object,
    preference: EnglishVarietyPreference = EnglishVarietyPreference.BOTH,
    user_card_id: int = 0,
) -> Card:
    """Build a Card from an oald entry + audio mapping row.

    ``word_us`` / ``word_gb`` always come from the entry (may be identical).
    ``preference`` only controls which English variety audio is attached.
    """
    data = dict(cast(Mapping[Any, Any], row))
    word_us = str(data["word_us"])
    word_gb = str(data["word_gb"])
    include_us = preference in {
        EnglishVarietyPreference.US,
        EnglishVarietyPreference.BOTH,
    }
    include_gb = preference in {
        EnglishVarietyPreference.GB,
        EnglishVarietyPreference.BOTH,
    }

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
            EnglishVarietyVariant(
                english_variety=EnglishVariety.US,
                word=word_us,
                ipa=ipa_at_position(
                    data.get("ipa_us") or (),
                    data.get("us_source_position"),
                ),
                audio=card_audio_from_row(data, prefix=EnglishVariety.US),
            )
            if include_us
            else None
        ),
        gb=(
            EnglishVarietyVariant(
                english_variety=EnglishVariety.GB,
                word=word_gb,
                ipa=ipa_at_position(
                    data.get("ipa_gb") or (),
                    data.get("gb_source_position"),
                ),
                audio=card_audio_from_row(data, prefix=EnglishVariety.GB),
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
    """Join translations in stored order, most important first."""
    if not isinstance(translations, Sequence) or isinstance(translations, (str, bytes)):
        return ""
    return ", ".join(
        value
        for value in dict.fromkeys(str(item).strip() for item in translations)
        if value
    )
