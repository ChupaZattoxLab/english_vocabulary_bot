"""User registration, settings, pause/block, and active-user queries."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from tgbot.db.mixins.base import EngineBound
from tgbot.db.models import (
    VALID_LEVELS,
    VALID_PRONUNCIATIONS,
    ActiveUser,
    BotUser,
    DatabaseError,
    as_db_row,
    as_db_rows,
    row_int,
    user_from_row,
)
from tgbot.db.schema import bot_users


class UsersMixin(EngineBound):
    async def upsert_user(
        self,
        telegram_user_id: int,
        chat_id: int,
        username: str,
        first_name: str,
    ) -> BotUser:
        stmt = pg_insert(bot_users).values(
            telegram_user_id=telegram_user_id,
            chat_id=chat_id,
            username=username,
            first_name=first_name,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[bot_users.c.telegram_user_id],
            set_={
                "chat_id": stmt.excluded.chat_id,
                "username": stmt.excluded.username,
                "first_name": stmt.excluded.first_name,
                "blocked_at": None,
                "is_active": sa.case(
                    (
                        sa.and_(
                            bot_users.c.paused_at.is_(None),
                            bot_users.c.onboarding_completed.is_(True),
                        ),
                        True,
                    ),
                    else_=bot_users.c.is_active,
                ),
                "updated_at": sa.func.current_timestamp(),
            },
        ).returning(*bot_users.c)

        async with self.engine.begin() as connection:
            row = (await connection.execute(stmt)).mappings().one()

        return user_from_row(as_db_row(row))

    async def get_user(self, telegram_user_id: int) -> BotUser | None:
        async with self.engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        sa.select(bot_users).where(
                            bot_users.c.telegram_user_id == telegram_user_id
                        )
                    )
                )
                .mappings()
                .first()
            )

        return user_from_row(as_db_row(row)) if row else None

    async def toggle_level(self, telegram_user_id: int, level: str) -> BotUser:
        normalized = level.lower()
        if normalized not in VALID_LEVELS:
            raise ValueError(f"unsupported CEFR level {level!r}")

        level_value = sa.literal(normalized)
        stmt = (
            sa.update(bot_users)
            .where(bot_users.c.telegram_user_id == telegram_user_id)
            .values(
                selected_levels=sa.case(
                    (
                        level_value == sa.any_(bot_users.c.selected_levels),
                        sa.func.array_remove(bot_users.c.selected_levels, level_value),
                    ),
                    else_=sa.func.array_append(
                        bot_users.c.selected_levels, level_value
                    ),
                ),
                updated_at=sa.func.current_timestamp(),
            )
            .returning(*bot_users.c)
        )

        async with self.engine.begin() as connection:
            row = (await connection.execute(stmt)).mappings().first()

        if not row:
            raise DatabaseError("bot user does not exist")

        return user_from_row(as_db_row(row))

    async def set_pronunciation(
        self,
        telegram_user_id: int,
        dialect: str,
    ) -> BotUser:
        normalized = dialect.lower()
        if normalized not in VALID_PRONUNCIATIONS:
            raise ValueError(f"unsupported pronunciation {dialect!r}")

        has_levels = sa.func.cardinality(bot_users.c.selected_levels) > 0
        stmt = (
            sa.update(bot_users)
            .where(bot_users.c.telegram_user_id == telegram_user_id)
            .values(
                pronunciation=normalized,
                onboarding_completed=has_levels,
                is_active=sa.case(
                    (
                        sa.or_(
                            bot_users.c.paused_at.is_not(None),
                            bot_users.c.blocked_at.is_not(None),
                        ),
                        False,
                    ),
                    else_=has_levels,
                ),
                updated_at=sa.func.current_timestamp(),
            )
            .returning(*bot_users.c)
        )

        async with self.engine.begin() as connection:
            row = (await connection.execute(stmt)).mappings().first()

        if not row:
            raise DatabaseError("bot user does not exist")

        return user_from_row(as_db_row(row))

    async def clear_blocked_marker(self, telegram_user_id: int) -> None:
        """Clear blocked_at after the user messages again; do not resume schedule."""
        async with self.engine.begin() as connection:
            await connection.execute(
                sa.update(bot_users)
                .where(
                    bot_users.c.telegram_user_id == telegram_user_id,
                    bot_users.c.blocked_at.is_not(None),
                )
                .values(
                    blocked_at=None,
                    updated_at=sa.func.current_timestamp(),
                )
            )

    async def set_active(self, telegram_user_id: int, active: bool) -> bool:
        values: dict[str, object] = {
            "is_active": active,
            "updated_at": sa.func.current_timestamp(),
        }
        if active:
            values["paused_at"] = None
            values["blocked_at"] = None
        else:
            values["paused_at"] = sa.func.current_timestamp()

        async with self.engine.begin() as connection:
            result = await connection.execute(
                sa.update(bot_users)
                .where(
                    bot_users.c.telegram_user_id == telegram_user_id,
                    bot_users.c.onboarding_completed.is_(True),
                )
                .values(**values)
            )

        return (result.rowcount or 0) > 0

    async def active_users(self) -> list[ActiveUser]:
        async with self.engine.connect() as connection:
            rows = (
                (
                    await connection.execute(
                        sa.select(
                            bot_users.c.telegram_user_id,
                            bot_users.c.chat_id,
                        )
                        .where(
                            bot_users.c.is_active.is_(True),
                            bot_users.c.onboarding_completed.is_(True),
                            sa.func.cardinality(bot_users.c.selected_levels) > 0,
                            bot_users.c.pronunciation.is_not(None),
                        )
                        .order_by(bot_users.c.telegram_user_id)
                    )
                )
                .mappings()
                .all()
            )

        return [
            ActiveUser(
                telegram_user_id=row_int(row, "telegram_user_id"),
                chat_id=row_int(row, "chat_id"),
            )
            for row in as_db_rows(rows)
        ]

    async def deactivate_user(self, telegram_user_id: int) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                sa.update(bot_users)
                .where(bot_users.c.telegram_user_id == telegram_user_id)
                .values(
                    is_active=False,
                    blocked_at=sa.func.current_timestamp(),
                    updated_at=sa.func.current_timestamp(),
                )
            )
