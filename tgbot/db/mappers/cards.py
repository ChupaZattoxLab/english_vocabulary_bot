"""Map query rows onto card models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from tgbot.db.mappers.values import (
    as_db_row,
    row_bytes,
    row_int,
    row_str,
    row_str_sequence,
)
from tgbot.models import (
    Card,
    CardAudio,
    DialectPreference,
    DialectVariant,
)


def card_from_row(
    row: object,
    preference: DialectPreference,
    user_card_id: int,
) -> Card:
    data = as_db_row(row)

    ipa_us_values = row_str_sequence(data, "ipa_us") if data["ipa_us"] else ()
    ipa_gb_values = row_str_sequence(data, "ipa_gb") if data["ipa_gb"] else ()
    us_position = data["us_source_position"]
    gb_position = data["gb_source_position"]
    ipa_us = selected_ipa(
        ipa_us_values,
        us_position if isinstance(us_position, int) else None,
    )
    ipa_gb = selected_ipa(
        ipa_gb_values,
        gb_position if isinstance(gb_position, int) else None,
    )

    translations = data["translations"]
    translation_source = (
        cast(Mapping[str, object], translations)
        if isinstance(translations, Mapping)
        else None
    )

    include_us = preference in {"us", "both"}
    include_gb = preference in {"gb", "both"}

    return Card(
        user_card_id=user_card_id,
        entry_id=row_int(data, "entry_id"),
        lexical_category=row_str(data, "lexical_category"),
        cefr=row_str(data, "cefr").upper(),
        definition=row_str(data, "definition"),
        example=row_str(data, "example"),
        translation=translation_text(translation_source),
        us=(
            DialectVariant(
                dialect="us",
                word=row_str(data, "word_us"),
                ipa=ipa_us,
                audio=CardAudio(
                    source_url=row_str(data, "us_source_url"),
                    audio_data=row_bytes(data, "us_audio_data"),
                    content_type=row_str(data, "us_content_type"),
                    filename=row_str(data, "us_filename"),
                ),
            )
            if include_us
            else None
        ),
        gb=(
            DialectVariant(
                dialect="gb",
                word=row_str(data, "word_gb"),
                ipa=ipa_gb,
                audio=CardAudio(
                    source_url=row_str(data, "gb_source_url"),
                    audio_data=row_bytes(data, "gb_audio_data"),
                    content_type=row_str(data, "gb_content_type"),
                    filename=row_str(data, "gb_filename"),
                ),
            )
            if include_gb
            else None
        ),
    )


def selected_ipa(values: Sequence[str], position: int | None) -> str:
    if not values:
        return ""

    if position is not None and 0 <= position < len(values):
        return str(values[position])

    return str(values[0])


def translation_text(translations: Mapping[str, object] | None) -> str:
    russian_raw = (translations or {}).get("ru")
    russian = russian_raw if isinstance(russian_raw, Mapping) else {}

    values = [str(russian.get("main") or "").strip()]
    also = russian.get("also") or []

    if isinstance(also, Sequence) and not isinstance(also, (str, bytes)):
        values.extend(str(value).strip() for value in also)

    return ", ".join(value for value in dict.fromkeys(values) if value)
