"""Synchronous SQLAlchemy helpers for scripts and tests.

Accepts the same ``postgresql+psycopg://`` URLs as the async bot engine.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine, make_url


def sync_engine(
    db_url: str,
    *,
    autocommit: bool = False,
    connect_timeout: int | None = None,
) -> Engine:
    connect_args: dict[str, Any] = {}
    if connect_timeout is not None:
        connect_args["connect_timeout"] = connect_timeout

    url = make_url(db_url)
    if url.host == "localhost":
        connect_args["hostaddr"] = "127.0.0.1"

    kwargs: dict[str, Any] = {}
    if connect_args:
        kwargs["connect_args"] = connect_args
    if autocommit:
        kwargs["isolation_level"] = "AUTOCOMMIT"
    return create_engine(db_url, **kwargs)


@contextmanager
def sync_connection(
    db_url: str,
    *,
    autocommit: bool = False,
    connect_timeout: int | None = None,
) -> Iterator[Connection]:
    engine = sync_engine(
        db_url,
        autocommit=autocommit,
        connect_timeout=connect_timeout,
    )
    try:
        if autocommit:
            with engine.connect() as connection:
                yield connection
        else:
            with engine.begin() as connection:
                yield connection
    finally:
        engine.dispose()
