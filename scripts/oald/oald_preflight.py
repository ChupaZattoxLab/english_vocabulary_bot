"""Preflight checks for scripts that consume the migrated OALD schema."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

OALD_TABLES = frozenset(
    {
        "oald_entries",
        "oald_audio_files",
        "oald_entry_audio_sources",
        "oald_audio_variants",
    }
)


class SchemaNotMigratedError(RuntimeError):
    """Raised when a build script runs before Alembic migrations."""


def require_oald_schema(cursor: Any) -> None:
    require_tables(cursor, OALD_TABLES)


def require_tables(cursor: Any, table_names: Iterable[str]) -> None:
    expected = set(table_names)
    cursor.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
          AND table_name = ANY(%s)
        """,
        (list(expected),),
    )
    existing = {str(row[0]) for row in cursor.fetchall()}
    missing = expected - existing
    if missing:
        raise SchemaNotMigratedError(
            "Database schema is incomplete; missing tables: "
            f"{', '.join(sorted(missing))}. Run "
            "`uv run migrate` first."
        )
