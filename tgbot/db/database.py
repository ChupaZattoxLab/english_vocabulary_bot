"""Async PostgreSQL access for users, delivery history, and OALD cards."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse

import sqlalchemy as sa
from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from tgbot.constants import (
    DB_CONNECT_TIMEOUT_SECONDS,
    DB_POOL_RECYCLE_SECONDS,
    DB_POOL_SIZE,
)
from tgbot.db.models import (
    DatabaseError,
    as_db_row,
    as_db_rows,
    row_optional_str,
    row_str,
)
from tgbot.db.queries import (
    AdminQueries,
    CardsQueries,
    SchedulerQueries,
    UsersQueries,
)
from tgbot.db.schema import MANAGED_TABLES
from tgbot.secrets import PROJECT_ROOT

_information_schema_tables = sa.table(
    "tables",
    sa.column("table_schema", sa.Text),
    sa.column("table_name", sa.Text),
    schema="information_schema",
)
_alembic_version = sa.table(
    "alembic_version",
    sa.column("version_num", sa.Text),
)


class Database(UsersQueries, CardsQueries, SchedulerQueries, AdminQueries):
    def __init__(
        self,
        db_url: str,
        pool_size: int = DB_POOL_SIZE,
    ):
        connect_args: dict[str, object] = {
            "connect_timeout": DB_CONNECT_TIMEOUT_SECONDS,
        }
        parsed = urlparse(db_url)
        if parsed.hostname == "localhost":
            connect_args["hostaddr"] = "127.0.0.1"

        self.engine: AsyncEngine = create_async_engine(
            db_url,
            pool_size=pool_size,
            # Headroom for concurrent deliveries + scheduler bookkeeping.
            max_overflow=pool_size,
            pool_pre_ping=True,
            pool_recycle=DB_POOL_RECYCLE_SECONDS,
            connect_args=connect_args,
        )

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
            rows = (
                (
                    await connection.execute(
                        sa.select(_information_schema_tables.c.table_name).where(
                            _information_schema_tables.c.table_schema == "public",
                            _information_schema_tables.c.table_name.in_(
                                list(MANAGED_TABLES)
                            ),
                        )
                    )
                )
                .mappings()
                .all()
            )
            existing = {
                row_str(as_db_row(row), "table_name") for row in as_db_rows(rows)
            }
            missing = MANAGED_TABLES - existing

            if missing:
                raise DatabaseError(
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
            if (
                not version_table
                or row_optional_str(as_db_row(version_table), "name") is None
            ):
                raise DatabaseError(
                    "Database is not managed by Alembic. Run `uv run migrate`."
                )

            version = (
                (await connection.execute(sa.select(_alembic_version.c.version_num)))
                .mappings()
                .first()
            )
            expected = migration_head()
            current = (
                row_str(as_db_row(version), "version_num") if version else "<none>"
            )

            if current != expected:
                raise DatabaseError(
                    f"Database migration is {current}, expected {expected}. "
                    "Run `uv run migrate`."
                )


@lru_cache(maxsize=1)
def migration_head() -> str:
    config = AlembicConfig(str(PROJECT_ROOT / "alembic.ini"))
    head = ScriptDirectory.from_config(config).get_current_head()

    if head is None:
        raise DatabaseError("Alembic has no migration head revision")

    return head
