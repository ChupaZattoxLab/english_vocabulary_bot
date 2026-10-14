"""Vocabulary card models for delivery."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any, cast

from tgbot.db.types import EnglishVariety, EnglishVarietyPreference

PREVIEW_USER_CARD_ID = uuid.UUID(int=0)


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
    user_card_id: uuid.UUID
    entry_id: uuid.UUID
    word_us: str
    word_gb: str
    lexical_category: str
    cefr: str
    definition: str
    example: str
    translation: str
    us: EnglishVarietyVariant | None
    gb: EnglishVarietyVariant | None
    # Later prepared tracks, in source order, so a both-pair can be chosen.
    # A card that is sent has these empty: one variety is a single track.
    us_more: tuple[EnglishVarietyVariant, ...] = ()
    gb_more: tuple[EnglishVarietyVariant, ...] = ()

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

    def variety_tracks(
        self, variety: EnglishVariety
    ) -> tuple[EnglishVarietyVariant, ...]:
        """Prepared tracks of one variety, earliest source position first."""
        if variety == EnglishVariety.US:
            primary, extra = self.us, self.us_more
        else:
            primary, extra = self.gb, self.gb_more
        if primary is None:
            return ()
        return (primary, *extra)

    def variants(self) -> tuple[EnglishVarietyVariant, ...]:
        """Voices in send order: US tracks, then GB tracks."""
        return self.variety_tracks(EnglishVariety.US) + self.variety_tracks(
            EnglishVariety.GB
        )

    def for_preference(self, preference: EnglishVarietyPreference) -> Card:
        """Copy with only the pronunciations this preference sends."""
        us_tracks = self.variety_tracks(EnglishVariety.US)
        gb_tracks = self.variety_tracks(EnglishVariety.GB)
        us_index, gb_index = choose_preference_tracks(
            preference,
            [track.ipa for track in us_tracks],
            [track.ipa for track in gb_tracks],
        ) or (None, None)
        return replace(
            self,
            us=us_tracks[us_index] if us_index is not None else None,
            gb=gb_tracks[gb_index] if gb_index is not None else None,
            us_more=(),
            gb_more=(),
        )


def card_from_row(
    row: object,
    preference: EnglishVarietyPreference = EnglishVarietyPreference.BOTH,
    user_card_id: uuid.UUID = PREVIEW_USER_CARD_ID,
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
    if "selected_us" in data or "selected_gb" in data:
        us_variants = (
            variants_from_selected(data.get("selected_us"), EnglishVariety.US, word_us)
            if include_us
            else []
        )
        gb_variants = (
            variants_from_selected(data.get("selected_gb"), EnglishVariety.GB, word_gb)
            if include_gb
            else []
        )
        us = us_variants[0] if us_variants else None
        gb = gb_variants[0] if gb_variants else None
        us_more = tuple(us_variants[1:])
        gb_more = tuple(gb_variants[1:])
    else:
        us = (
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
        )
        gb = (
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
        )
        us_more = ()
        gb_more = ()

    return Card(
        user_card_id=user_card_id,
        entry_id=as_uuid(data["entry_id"]),
        word_us=word_us,
        word_gb=word_gb,
        lexical_category=str(data["lexical_category"]),
        cefr=str(data["cefr"]).upper(),
        definition=str(data.get("definition") or ""),
        example=str(data.get("example") or ""),
        translation=russian_translation(data.get("translations")),
        us=us,
        gb=gb,
        us_more=us_more,
        gb_more=gb_more,
    )


def as_uuid(value: object) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    return uuid.UUID(str(value))


def card_audio_from_row(data: Mapping[Any, Any], *, prefix: str) -> CardAudio:
    return card_audio_from_mapping(
        {
            "source_url": data.get(f"{prefix}_source_url"),
            "audio_data": data.get(f"{prefix}_audio_data"),
            "content_type": data.get(f"{prefix}_content_type"),
            "filename": data.get(f"{prefix}_filename"),
        }
    )


def card_audio_from_mapping(item: Mapping[Any, Any]) -> CardAudio:
    raw = item.get("audio_data") or b""
    if isinstance(raw, memoryview):
        audio_data = raw.tobytes()
    else:
        audio_data = bytes(raw)

    return CardAudio(
        source_url=str(item.get("source_url") or ""),
        audio_data=audio_data,
        content_type=str(item.get("content_type") or ""),
        filename=str(item.get("filename") or ""),
    )


def variants_from_selected(
    value: object,
    english_variety: EnglishVariety,
    word: str,
) -> list[EnglishVarietyVariant]:
    """Build variants from the pronunciations chosen for one variety."""
    if not isinstance(value, list):
        return []

    variants: list[EnglishVarietyVariant] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        variants.append(
            EnglishVarietyVariant(
                english_variety=english_variety,
                word=word,
                ipa=str(item.get("ipa") or ""),
                audio=card_audio_from_mapping(item),
            )
        )
    return variants


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


def choose_preference_tracks(
    preference: EnglishVarietyPreference,
    us_ipas: Sequence[str],
    gb_ipas: Sequence[str],
) -> tuple[int | None, int | None] | None:
    """Indexes into the source-ordered IPA lists: ``(us, gb)``.
    None when a required variety has no track. A single variety is index 0.
    """
    if preference == EnglishVarietyPreference.US:
        return (0, None) if us_ipas else None
    if preference == EnglishVarietyPreference.GB:
        return (None, 0) if gb_ipas else None

    pair = choose_cross_variety_pair(gb_ipas, us_ipas)
    if pair is None:
        return None
    gb_index, us_index = pair
    return us_index, gb_index


def choose_cross_variety_pair(
    gb_ipas: Sequence[str],
    us_ipas: Sequence[str],
) -> tuple[int, int] | None:
    """GB-anchored pair for the "both" preference: ``(gb_index, us_index)``.
    Lists are in source order. Walk GB and take the first US whose IPA
    differs. When every pair matches, return the first of each list.
    """
    if not gb_ipas or not us_ipas:
        return None

    for gb_index, gb_ipa in enumerate(gb_ipas):
        for us_index, us_ipa in enumerate(us_ipas):
            if gb_ipa.strip() != us_ipa.strip():
                return gb_index, us_index

    return 0, 0


def russian_translation(translations: object) -> str:
    """Join translations in stored order, most important first."""
    if not isinstance(translations, Sequence) or isinstance(translations, (str, bytes)):
        return ""
    return ", ".join(
        value
        for value in dict.fromkeys(str(item).strip() for item in translations)
        if value
    )
