"""Map query rows onto reserved card models."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import cast

from tgbot.db.domain import (
    VALID_PRONUNCIATIONS,
    CardDialect,
    ReservedAudio,
    ReservedCard,
)
from tgbot.db.mappers.values import (
    as_db_row,
    row_bytes,
    row_int,
    row_str,
    row_str_sequence,
)


def card_from_row(
    row: object,
    dialect: str,
    history_id: int,
) -> ReservedCard:
    data = as_db_row(row)
    normalized = dialect.lower()
    if normalized not in VALID_PRONUNCIATIONS:
        raise ValueError(f"unsupported pronunciation {dialect!r}")

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

    primary_prefix = "gb" if normalized == "gb" else "us"
    card_dialect = cast(CardDialect, normalized.upper())
    translations = data["translations"]
    translation_source = (
        cast(Mapping[str, object], translations)
        if isinstance(translations, Mapping)
        else None
    )

    return ReservedCard(
        history_id=history_id,
        entry_id=row_int(data, "entry_id"),
        word=row_str(data, f"word_{primary_prefix}"),
        lexical_category=row_str(data, "lexical_category"),
        cefr=row_str(data, "cefr").upper(),
        definition=row_str(data, "definition"),
        example=row_str(data, "example"),
        ipa=ipa_gb if normalized == "gb" else ipa_us,
        dialect=card_dialect,
        translation=translation_text(translation_source),
        source_url=row_str(data, f"{primary_prefix}_source_url"),
        audio_data=row_bytes(data, f"{primary_prefix}_audio_data"),
        content_type=row_str(data, f"{primary_prefix}_content_type"),
        filename=row_str(data, f"{primary_prefix}_filename"),
        word_us=row_str(data, "word_us"),
        word_gb=row_str(data, "word_gb"),
        ipa_us=ipa_us,
        ipa_gb=ipa_gb,
        secondary_audio=(
            ReservedAudio(
                dialect="GB",
                source_url=row_str(data, "gb_source_url"),
                audio_data=row_bytes(data, "gb_audio_data"),
                content_type=row_str(data, "gb_content_type"),
                filename=row_str(data, "gb_filename"),
            )
            if normalized == "both"
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
