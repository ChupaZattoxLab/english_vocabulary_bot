"""Dataclasses and row mappers for bot database access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, cast

CefrLevel = Literal["a1", "a2", "b1", "b2", "c1", "c2"]
Pronunciation = Literal["us", "gb", "both"]
CardDialect = Literal["US", "GB", "BOTH"]

VALID_LEVELS: tuple[CefrLevel, ...] = ("a1", "a2", "b1", "b2", "c1", "c2")
VALID_PRONUNCIATIONS: frozenset[Pronunciation] = frozenset({"us", "gb", "both"})


class DatabaseError(RuntimeError):
    """Raised when the bot database cannot be initialized safely."""


@dataclass(frozen=True)
class BotUser:
    telegram_user_id: int
    chat_id: int
    username: str
    first_name: str
    selected_levels: tuple[str, ...]
    pronunciation: str | None
    onboarding_completed: bool
    is_active: bool


@dataclass(frozen=True)
class ActiveUser:
    telegram_user_id: int
    chat_id: int


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


def user_from_row(row: dict[str, Any]) -> BotUser:
    return BotUser(
        telegram_user_id=int(row["telegram_user_id"]),
        chat_id=int(row["chat_id"]),
        username=str(row["username"]),
        first_name=str(row["first_name"]),
        selected_levels=tuple(row["selected_levels"]),
        pronunciation=row["pronunciation"],
        onboarding_completed=bool(row["onboarding_completed"]),
        is_active=bool(row["is_active"]),
    )


def selected_ipa(values: list[str], position: int | None) -> str:
    if not values:
        return ""
    if position is not None and 0 <= position < len(values):
        return str(values[position])
    return str(values[0])


def translation_text(translations: dict[str, Any] | None) -> str:
    russian = (translations or {}).get("ru") or {}
    values = [str(russian.get("main") or "").strip()]
    values.extend(str(value).strip() for value in russian.get("also") or [])
    return ", ".join(value for value in dict.fromkeys(values) if value)


def card_from_row(
    row: dict[str, Any],
    *,
    dialect: str,
    history_id: int,
) -> ReservedCard:
    normalized = dialect.lower()
    if normalized not in VALID_PRONUNCIATIONS:
        raise ValueError(f"unsupported pronunciation {dialect!r}")
    ipa_us = selected_ipa(row["ipa_us"], row["us_source_position"])
    ipa_gb = selected_ipa(row["ipa_gb"], row["gb_source_position"])
    primary_prefix = "gb" if normalized == "gb" else "us"
    card_dialect = cast(CardDialect, normalized.upper())
    return ReservedCard(
        history_id=history_id,
        entry_id=int(row["entry_id"]),
        word=str(row[f"word_{primary_prefix}"]),
        lexical_category=str(row["lexical_category"]),
        cefr=str(row["cefr"]).upper(),
        definition=str(row["definition"]),
        example=str(row["example"]),
        ipa=ipa_gb if normalized == "gb" else ipa_us,
        dialect=card_dialect,
        translation=translation_text(row["translations"]),
        source_url=str(row[f"{primary_prefix}_source_url"]),
        audio_data=bytes(row[f"{primary_prefix}_audio_data"]),
        content_type=str(row[f"{primary_prefix}_content_type"]),
        filename=str(row[f"{primary_prefix}_filename"]),
        word_us=str(row["word_us"]),
        word_gb=str(row["word_gb"]),
        ipa_us=ipa_us,
        ipa_gb=ipa_gb,
        secondary_audio=(
            ReservedAudio(
                dialect="GB",
                source_url=str(row["gb_source_url"]),
                audio_data=bytes(row["gb_audio_data"]),
                content_type=str(row["gb_content_type"]),
                filename=str(row["gb_filename"]),
            )
            if normalized == "both"
            else None
        ),
    )
