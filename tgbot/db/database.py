"""Async PostgreSQL access for users, delivery history, and OALD cards."""

from __future__ import annotations

from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from tgbot.config import PROJECT_ROOT
from tgbot.db.mixins import (
    AdminMixin,
    CardsMixin,
    SchedulerMixin,
    UsersMixin,
)
from tgbot.db.models import DatabaseError
from tgbot.db.schema import MANAGED_TABLES


@lru_cache(maxsize=1)
def migration_head() -> str:
    config = AlembicConfig(str(PROJECT_ROOT / "alembic.ini"))
    return ScriptDirectory.from_config(config).get_current_head()


def _pool_kwargs(database_url: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "row_factory": dict_row,
        "connect_timeout": 10,
    }
    if urlparse(database_url).hostname == "localhost":
        kwargs["hostaddr"] = "127.0.0.1"
    return kwargs


class Database(UsersMixin, CardsMixin, SchedulerMixin, AdminMixin):
    def __init__(self, database_url: str, *, pool_size: int = 5):
        self.pool = AsyncConnectionPool(
            conninfo=database_url,
            kwargs=_pool_kwargs(database_url),
            min_size=1,
            max_size=pool_size,
            open=False,
            name="tgbot",
        )

    async def open(self) -> None:
        await self.pool.open(wait=True, timeout=30)
        try:
            await self.verify_schema()
        except Exception:
            await self.pool.close()
            raise

    async def close(self) -> None:
        await self.pool.close()

    async def verify_schema(self) -> None:
        async with self.pool.connection() as connection:
            rows = await (
                await connection.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = ANY(%s)
                    """,
                    (list(MANAGED_TABLES),),
                )
            ).fetchall()
            existing = {str(row["table_name"]) for row in rows}
            missing = MANAGED_TABLES - existing
            if missing:
                raise DatabaseError(
                    "Database schema is incomplete; missing tables: "
                    f"{', '.join(sorted(missing))}. Run "
                    "`uv run migrate`."
                )

            version_table = await (
                await connection.execute(
                    "SELECT to_regclass('public.alembic_version') AS name"
                )
            ).fetchone()
            if not version_table or version_table["name"] is None:
                raise DatabaseError(
                    "Database is not managed by Alembic. Run `uv run migrate`."
                )
            version = await (
                await connection.execute("SELECT version_num FROM alembic_version")
            ).fetchone()
            expected = migration_head()
            current = str(version["version_num"]) if version else "<none>"
            if current != expected:
                raise DatabaseError(
                    f"Database migration is {current}, expected {expected}. "
                    "Run `uv run migrate`."
                )
