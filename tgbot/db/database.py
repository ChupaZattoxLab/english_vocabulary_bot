"""Async PostgreSQL access for users, delivery history, and OALD cards."""

from __future__ import annotations

from functools import lru_cache

import sqlalchemy as sa
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import AsyncEngine

from tgbot.db.postgres import async_engine, missing_public_tables
from tgbot.db.queries import (
    AdminQueries,
    CardsQueries,
    SchedulerQueries,
    UsersQueries,
)
from tgbot.db.tables import MANAGED_TABLES
from tgbot.secrets import PROJECT_ROOT

# Alembic revision marker table written by migrations.
alembic_version = sa.table(
    "alembic_version",
    sa.column("version_num", sa.Text),
)


class Database(UsersQueries, CardsQueries, SchedulerQueries, AdminQueries):
    def __init__(
        self,
        db_url: str,
        pool_size: int,
    ):
        self.engine: AsyncEngine = async_engine(db_url, pool_size=pool_size)

    async def open(self) -> None:
        try:
            await self.verify_schema()
        except Exception:
            await self.engine.dispose()
            raise

    async def close(self) -> None:
        await self.engine.dispose()

    async def verify_schema(self) -> None:
        async with self.engine.connect() as connection:
            missing = await missing_public_tables(connection, MANAGED_TABLES)

            if missing:
                raise RuntimeError(
                    "Database schema is incomplete; missing tables: "
                    f"{', '.join(sorted(missing))}. Run "
                    "`uv run migrate`."
                )

            version_table = (
                (
                    await connection.execute(
                        sa.select(
                            sa.func.to_regclass("public.alembic_version").label("name")
                        )
                    )
                )
                .mappings()
                .first()
            )
            if not version_table or version_table["name"] is None:
                raise RuntimeError(
                    "Database is not managed by Alembic. Run `uv run migrate`."
                )

            version = (
                (await connection.execute(sa.select(alembic_version.c.version_num)))
                .mappings()
                .first()
            )
            expected = migration_head()
            current = str(version["version_num"]) if version else "<none>"

            if current != expected:
                raise RuntimeError(
                    f"Database migration is {current}, expected {expected}. "
                    "Run `uv run migrate`."
                )


@lru_cache(maxsize=1)
def migration_head() -> str:
    config = AlembicConfig(str(PROJECT_ROOT / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()

    if head is None:
        raise RuntimeError("Alembic has no migration head revision")

    return head
