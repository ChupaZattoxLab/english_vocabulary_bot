"""Shared database session helpers for query mixins."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any, cast

from sqlalchemy.engine import CursorResult, RowMapping
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine


class DbSession:
    """Async engine plus short helpers for common execute/fetch patterns.

    Read helpers open a non-transactional connection; write helpers use
    ``begin()`` so the statement commits on success.
    """

    engine: AsyncEngine

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[AsyncConnection]:
        """Read-only connection for one or more statements."""
        async with self.engine.connect() as connection:
            yield connection

    @asynccontextmanager
    async def begin(self) -> AsyncIterator[AsyncConnection]:
        """Transactional connection; commits on clean exit, rolls back on error."""
        async with self.engine.begin() as connection:
            yield connection

    async def fetch_first(self, statement: Any) -> RowMapping | None:
        """Run a read query and return the first mapping row, or ``None``."""
        async with self.connect() as connection:
            return await mapping_first(connection, statement)

    async def fetch_exactly_one(self, statement: Any) -> RowMapping:
        """Run a read query and return exactly one mapping row (else raise)."""
        async with self.connect() as connection:
            return await mapping_exactly_one(connection, statement)

    async def fetch_all(self, statement: Any) -> Sequence[RowMapping]:
        """Run a read query and return all mapping rows."""
        async with self.connect() as connection:
            return await mapping_all(connection, statement)

    async def fetch_scalar(self, statement: Any) -> object | None:
        """Run a read query and return a single column value, or ``None``."""
        async with self.connect() as connection:
            return (await connection.execute(statement)).scalar_one_or_none()

    async def fetch_scalars(self, statement: Any) -> Sequence[Any]:
        """Run a read query and return the first column of every row."""
        async with self.connect() as connection:
            return (await connection.execute(statement)).scalars().all()

    async def execute(self, statement: Any) -> CursorResult[Any]:
        """Run a write statement in a transaction and return the raw result."""
        async with self.begin() as connection:
            return cast(CursorResult[Any], await connection.execute(statement))

    async def execute_fetch_first(self, statement: Any) -> RowMapping | None:
        """Run a write (e.g. ``RETURNING``) and return the first mapping row."""
        async with self.begin() as connection:
            return await mapping_first(connection, statement)

    async def execute_fetch_exactly_one(self, statement: Any) -> RowMapping:
        """Run a write with ``RETURNING`` and require exactly one mapping row."""
        async with self.begin() as connection:
            return await mapping_exactly_one(connection, statement)


async def mapping_first(
    connection: AsyncConnection,
    statement: Any,
) -> RowMapping | None:
    """Execute on an open connection; return the first mapping row or ``None``."""
    return (await connection.execute(statement)).mappings().first()


async def mapping_exactly_one(
    connection: AsyncConnection,
    statement: Any,
) -> RowMapping:
    """Execute on an open connection; require exactly one mapping row."""
    return (await connection.execute(statement)).mappings().one()


async def mapping_all(
    connection: AsyncConnection,
    statement: Any,
) -> Sequence[RowMapping]:
    """Execute on an open connection; return all mapping rows."""
    return (await connection.execute(statement)).mappings().all()
