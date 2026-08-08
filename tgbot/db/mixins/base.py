"""Shared base for database mixins that require a connection pool."""

from __future__ import annotations

from psycopg_pool import AsyncConnectionPool


class PoolBound:
    """Declares the pool attribute that Database provides at runtime."""

    pool: AsyncConnectionPool
