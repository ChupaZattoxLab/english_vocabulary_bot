"""Typed accessors for SQLAlchemy/psycopg mapping rows."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import cast

DbRow = Mapping[str, object]


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
