"""Blocking (sync) SQLAlchemy access for CLI scripts and tests.

The Telegram bot uses async ``Database`` / ``AsyncEngine`` so it can await
Telegram I/O without blocking. Import/download scripts and pytest helpers are
plain synchronous code: they need a normal ``Engine`` that blocks until each
query finishes. Same ``postgresql+psycopg://`` URLs as the bot; only the
driver style differs (sync vs async).
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine, make_url
from sqlalchemy_utils import create_database, database_exists, drop_database

from tgbot.db.types import DB_CONNECT_TIMEOUT_SECONDS

pg_stat_activity = sa.table(
    "pg_stat_activity",
    sa.column("pid", sa.Integer),
    sa.column("datname", sa.Text),
)


def sync_engine(
    db_url: str,
    autocommit: bool = False,
) -> Engine:
    """Build a short-lived sync engine (caller must ``dispose()``)."""
    connect_args: dict[str, Any] = {
        "connect_timeout": DB_CONNECT_TIMEOUT_SECONDS,
    }

    kwargs: dict[str, Any] = {"connect_args": connect_args}
    if autocommit:
        # Catalog DDL (create/drop database) cannot run inside a transaction.
        kwargs["isolation_level"] = "AUTOCOMMIT"
    return create_engine(db_url, **kwargs)


@contextmanager
def sync_connection(
    db_url: str,
    autocommit: bool = False,
) -> Iterator[Connection]:
    """Open one connection, then dispose the engine.

    Default: one transaction for the whole ``with`` block (``begin``).
    ``autocommit=True``: each statement commits immediately (DDL / many small
    writes in download scripts).
    """
    engine = sync_engine(db_url, autocommit=autocommit)
    try:
        if autocommit:
            with engine.connect() as connection:
                yield connection
        else:
            with engine.begin() as connection:
                yield connection
    finally:
        engine.dispose()


def managed_database_url(
    db_url: str,
    admin_db_url: str | None = None,
) -> str:
    """URL whose credentials create/drop ``db_url``'s database name."""
    target = make_url(db_url)
    if not target.database:
        raise ValueError("database URL must include a database name")
    if admin_db_url is None:
        return target.render_as_string(hide_password=False)
    admin = make_url(admin_db_url)
    return admin.set(database=target.database).render_as_string(hide_password=False)


def ensure_database_exists(
    db_url: str,
    admin_db_url: str | None = None,
) -> bool:
    """Create the target database when missing. Returns True if created."""
    url = managed_database_url(db_url, admin_db_url)
    if database_exists(url):
        return False
    create_database(url)
    return True


def terminate_database_backends(db_url: str) -> None:
    """Disconnect other sessions from ``db_url``'s database (Postgres)."""
    url = make_url(db_url)
    database = url.database
    if not database:
        raise ValueError("database URL must include a database name")

    admin_url = url.set(database="postgres").render_as_string(hide_password=False)
    with sync_connection(admin_url, autocommit=True) as connection:
        connection.execute(
            sa.select(sa.func.pg_terminate_backend(pg_stat_activity.c.pid)).where(
                pg_stat_activity.c.datname == database,
                pg_stat_activity.c.pid != sa.func.pg_backend_pid(),
            )
        )


def destroy_database(
    db_url: str,
    admin_db_url: str | None = None,
) -> None:
    """Drop the target database after terminating other backends."""
    url = managed_database_url(db_url, admin_db_url)
    if not database_exists(url):
        return
    terminate_database_backends(url)
    drop_database(url)
