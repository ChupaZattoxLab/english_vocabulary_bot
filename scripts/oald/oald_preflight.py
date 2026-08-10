"""Preflight checks for scripts that consume the migrated OALD schema."""

from __future__ import annotations

from collections.abc import Iterable

import sqlalchemy as sa
from sqlalchemy.engine import Connection

from tgbot.db.tables import (
    oald_audio_files,
    oald_audio_variants,
    oald_entries,
    oald_entry_audio_sources,
    oxford_lexical_entries,
)

OALD_TABLES = frozenset(
    {
        oald_entries.name,
        oald_audio_files.name,
        oald_entry_audio_sources.name,
        oald_audio_variants.name,
    }
)

OXFORD_TABLES = frozenset({oxford_lexical_entries.name})


class SchemaNotMigratedError(RuntimeError):
    """Raised when a build script runs before Alembic migrations."""


def require_oald_schema(connection: Connection) -> None:
    require_tables(connection, OALD_TABLES)


def require_oxford_schema(connection: Connection) -> None:
    require_tables(connection, OXFORD_TABLES)


def require_tables(connection: Connection, table_names: Iterable[str]) -> None:
    expected = set(table_names)
    inspector = sa.inspect(connection)
    existing = {name for name in expected if inspector.has_table(name)}
    missing = expected - existing
    if missing:
        raise SchemaNotMigratedError(
            "Database schema is incomplete; missing tables: "
            f"{', '.join(sorted(missing))}. Run "
            "`uv run migrate` first."
        )
