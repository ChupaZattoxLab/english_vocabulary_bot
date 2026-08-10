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

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine, make_url

from tgbot.db.types import DB_CONNECT_TIMEOUT_SECONDS


def sync_engine(
    db_url: str,
    autocommit: bool = False,
) -> Engine:
    """Build a short-lived sync engine (caller must ``dispose()``)."""
    connect_args: dict[str, Any] = {
        "connect_timeout": DB_CONNECT_TIMEOUT_SECONDS,
    }

    url = make_url(db_url)
    if url.host == "localhost":
        # Avoid IPv6 localhost surprises on Windows.
        connect_args["hostaddr"] = "127.0.0.1"

    kwargs: dict[str, Any] = {"connect_args": connect_args}
    if autocommit:
        # Needed for CREATE/DROP DATABASE (cannot run inside a transaction).
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
