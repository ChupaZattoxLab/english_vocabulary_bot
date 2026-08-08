"""Dataclasses and row mappers for bot database access."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

CefrLevel = Literal["a1", "a2", "b1", "b2", "c1", "c2"]
Pronunciation = Literal["us", "gb", "both"]
CardDialect = Literal["US", "GB", "BOTH"]

VALID_LEVELS: tuple[CefrLevel, ...] = ("a1", "a2", "b1", "b2", "c1", "c2")
VALID_PRONUNCIATIONS: frozenset[Pronunciation] = frozenset({"us", "gb", "both"})

DbRow = Mapping[str, object]


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


@dataclass(frozen=True)
class AdminUsersSummary:
    total_users: int
    active_users: int
    paused_users: int
    blocked_users: int
    new_today: int
    new_week: int
    new_month: int
    levels: dict[str, int]
    dialects: dict[str, int]


@dataclass(frozen=True)
class AdminUserDetail:
    telegram_user_id: int
    chat_id: int
    username: str
    first_name: str
    selected_levels: tuple[str, ...]
    pronunciation: str | None
    onboarding_completed: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime
    last_delivery_at: datetime | None
    paused_at: datetime | None
    blocked_at: datetime | None
    delivered_cards: int
    last_successful_delivery: datetime | None


@dataclass(frozen=True)
class AdminContentSummary:
    ready_entries: int


@dataclass(frozen=True)
class AdminWordMatch:
    id: int
    word_us: str
    word_gb: str
    lexical_category: str
    cefr: str


def user_from_row(row: object) -> BotUser:
    data = as_db_row(row)

    return BotUser(
        telegram_user_id=row_int(data, "telegram_user_id"),
        chat_id=row_int(data, "chat_id"),
        username=row_str(data, "username"),
        first_name=row_str(data, "first_name"),
        selected_levels=row_str_sequence(data, "selected_levels"),
        pronunciation=row_optional_str(data, "pronunciation"),
        onboarding_completed=row_bool(data, "onboarding_completed"),
        is_active=row_bool(data, "is_active"),
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


def admin_user_detail_from_row(row: object) -> AdminUserDetail:
    data = as_db_row(row)

    return AdminUserDetail(
        telegram_user_id=row_int(data, "telegram_user_id"),
        chat_id=row_int(data, "chat_id"),
        username=row_str(data, "username"),
        first_name=row_str(data, "first_name"),
        selected_levels=row_str_sequence(data, "selected_levels"),
        pronunciation=row_optional_str(data, "pronunciation"),
        onboarding_completed=row_bool(data, "onboarding_completed"),
        is_active=row_bool(data, "is_active"),
        created_at=row_datetime(data, "created_at"),
        updated_at=row_datetime(data, "updated_at"),
        last_delivery_at=row_optional_datetime(data, "last_delivery_at"),
        paused_at=row_optional_datetime(data, "paused_at"),
        blocked_at=row_optional_datetime(data, "blocked_at"),
        delivered_cards=row_int(data, "delivered_cards")
        if data["delivered_cards"] is not None
        else 0,
        last_successful_delivery=row_optional_datetime(
            data,
            "last_successful_delivery",
        ),
    )


def admin_word_match_from_row(row: object) -> AdminWordMatch:
    data = as_db_row(row)

    return AdminWordMatch(
        id=row_int(data, "id"),
        word_us=row_str(data, "word_us"),
        word_gb=row_str(data, "word_gb"),
        lexical_category=row_str(data, "lexical_category"),
        cefr=row_str(data, "cefr"),
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


def as_db_row(row: object) -> DbRow:
    """Cast a mapping-like query row to a typed mapping."""
    return cast(DbRow, row)


def as_db_rows(rows: object) -> tuple[DbRow, ...]:
    return tuple(as_db_row(row) for row in cast(Sequence[object], rows))


def row_int(row: DbRow, key: str) -> int:
    value = row[key]

    if isinstance(value, bool) or value is None:
        raise TypeError(f"row[{key!r}] is not an int: {value!r}")

    if isinstance(value, int):
        return value

    if isinstance(value, (str, float)):
        return int(value)

    raise TypeError(f"row[{key!r}] is not an int: {type(value)!r}")


def row_str(row: DbRow, key: str) -> str:
    value = row[key]

    if value is None:
        return ""

    return str(value)


def row_optional_str(row: DbRow, key: str) -> str | None:
    value = row[key]

    return None if value is None else str(value)


def row_bool(row: DbRow, key: str) -> bool:
    return bool(row[key])


def row_bytes(row: DbRow, key: str) -> bytes:
    value = row[key]

    if isinstance(value, memoryview):
        return value.tobytes()

    if isinstance(value, (bytes, bytearray)):
        return bytes(value)

    raise TypeError(f"row[{key!r}] is not bytes: {type(value)!r}")


def row_datetime(row: DbRow, key: str) -> datetime:
    value = row[key]

    if not isinstance(value, datetime):
        raise TypeError(f"row[{key!r}] is not datetime: {type(value)!r}")

    return value


def row_optional_datetime(row: DbRow, key: str) -> datetime | None:
    value = row[key]

    if value is None:
        return None

    if not isinstance(value, datetime):
        raise TypeError(f"row[{key!r}] is not datetime: {type(value)!r}")

    return value


def row_str_sequence(row: DbRow, key: str) -> tuple[str, ...]:
    value = row[key] or ()

    if isinstance(value, str) or not isinstance(value, Sequence):
        raise TypeError(f"row[{key!r}] is not a string sequence: {type(value)!r}")

    return tuple(str(item) for item in value)
