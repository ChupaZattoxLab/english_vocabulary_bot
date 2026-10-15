"""Async PostgreSQL engine for the bot, scripts, tests, and Alembic."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import Any

import sqlalchemy as sa
from sqlalchemy import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import DDLElement
from sqlalchemy.sql.compiler import DDLCompiler

from tgbot.db.types import DB_CONNECT_TIMEOUT_SECONDS, DB_POOL_RECYCLE_SECONDS

information_schema_tables = sa.table(
    "tables",
    sa.column("table_schema", sa.Text),
    sa.column("table_name", sa.Text),
    schema="information_schema",
)

pg_database = sa.table(
    "pg_database",
    sa.column("datname", sa.Text),
)

pg_stat_activity = sa.table(
    "pg_stat_activity",
    sa.column("pid", sa.Integer),
    sa.column("datname", sa.Text),
)


class CreateDatabase(DDLElement):
    """``CREATE DATABASE`` — the name cannot be a bind parameter."""

    inherit_cache = False

    def __init__(self, name: str) -> None:
        self.name = name


class DropDatabase(DDLElement):
    """``DROP DATABASE`` — the name cannot be a bind parameter."""

    inherit_cache = False

    def __init__(self, name: str) -> None:
        self.name = name


@compiles(CreateDatabase, "postgresql")
def compile_create_database(
    element: CreateDatabase,
    compiler: DDLCompiler,
    **kwargs: Any,
) -> str:
    return "CREATE DATABASE " + compiler.preparer.quote(element.name)


@compiles(DropDatabase, "postgresql")
def compile_drop_database(
    element: DropDatabase,
    compiler: DDLCompiler,
    **kwargs: Any,
) -> str:
    return "DROP DATABASE " + compiler.preparer.quote(element.name)


@asynccontextmanager
async def async_connection(
    db_url: str,
    autocommit: bool = False,
) -> AsyncIterator[AsyncConnection]:
    """Open one connection, then dispose the engine.

    Default: one transaction for the whole ``async with`` block.
    ``autocommit=True``: each statement commits immediately.
    """
    engine = async_engine(db_url, autocommit=autocommit)
    try:
        if autocommit:
            async with engine.connect() as connection:
                yield connection
        else:
            async with engine.begin() as connection:
                yield connection
    finally:
        await engine.dispose()


def async_engine(
    db_url: str,
    *,
    pool_size: int | None = None,
    autocommit: bool = False,
) -> AsyncEngine:
    """Async engine: ``NullPool`` unless ``pool_size`` is set."""
    kwargs: dict[str, Any] = {
        "connect_args": {"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS},
    }
    if autocommit:
        # Catalog DDL (create/drop database) cannot run inside a transaction.
        kwargs["isolation_level"] = "AUTOCOMMIT"
    if pool_size is None:
        kwargs["poolclass"] = NullPool
    else:
        # Headroom for concurrent deliveries + scheduler bookkeeping.
        kwargs["pool_size"] = pool_size
        kwargs["max_overflow"] = pool_size
        kwargs["pool_pre_ping"] = True
        kwargs["pool_recycle"] = DB_POOL_RECYCLE_SECONDS
    return create_async_engine(db_url, **kwargs)


async def missing_public_tables(
    connection: AsyncConnection,
    table_names: Iterable[str],
) -> set[str]:
    """Public tables from ``table_names`` that are not in the database."""
    expected = set(table_names)
    rows = await connection.scalars(
        sa.select(information_schema_tables.c.table_name).where(
            information_schema_tables.c.table_schema == "public",
            information_schema_tables.c.table_name.in_(expected),
        )
    )
    return expected - set(rows.all())


@asynccontextmanager
async def maintenance_connection(
    db_url: str,
    admin_db_url: str | None = None,
) -> AsyncIterator[tuple[AsyncConnection, str]]:
    """Autocommit connection to database ``postgres``, plus the target name."""
    target = make_url(db_url)
    database = target.database
    if not database:
        raise ValueError("database URL must include a database name")
    admin = target if admin_db_url is None else make_url(admin_db_url)
    engine = async_engine(
        admin.set(database="postgres").render_as_string(hide_password=False),
        autocommit=True,
    )
    try:
        async with engine.connect() as connection:
            yield connection, database
    finally:
        await engine.dispose()


async def ensure_database_exists(
    db_url: str,
    admin_db_url: str | None = None,
) -> bool:
    """Create the target database when missing. Returns True if created."""
    async with maintenance_connection(db_url, admin_db_url) as (connection, database):
        if await database_exists(connection, database):
            return False
        await connection.execute(CreateDatabase(database))
        return True


async def destroy_database(
    db_url: str,
    admin_db_url: str | None = None,
) -> None:
    """Drop the target database after terminating other backends."""
    async with maintenance_connection(db_url, admin_db_url) as (connection, database):
        await connection.execute(
            sa.select(sa.func.pg_terminate_backend(pg_stat_activity.c.pid)).where(
                pg_stat_activity.c.datname == database,
                pg_stat_activity.c.pid != sa.func.pg_backend_pid(),
            )
        )
        await connection.execute(DropDatabase(database))


async def database_exists(connection: AsyncConnection, database: str) -> bool:
    """True when ``pg_database`` has ``database``."""
    found = await connection.scalar(
        sa.select(sa.literal(1)).where(pg_database.c.datname == database)
    )
    return found is not None
