"""Preflight checks for scripts that consume the migrated OALD schema."""

from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy.ext.asyncio import AsyncConnection

from tgbot.db.postgres import missing_public_tables
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


async def require_oald_schema(connection: AsyncConnection) -> None:
    await require_tables(connection, OALD_TABLES)


async def require_oxford_schema(connection: AsyncConnection) -> None:
    await require_tables(connection, OXFORD_TABLES)


async def require_tables(
    connection: AsyncConnection,
    table_names: Iterable[str],
) -> None:
    missing = await missing_public_tables(connection, table_names)
    if missing:
        raise SchemaNotMigratedError(
            "Database schema is incomplete; missing tables: "
            f"{', '.join(sorted(missing))}. Run "
            "`uv run migrate` first."
        )
