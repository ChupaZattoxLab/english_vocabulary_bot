"""User registration, settings, pause/block, and active-user queries."""

from __future__ import annotations

from typing import cast

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from tgbot.db.models import (
    ActiveUser,
    CefrLevel,
    DialectPreference,
    active_user_from_row,
)
from tgbot.db.queries.base import DbSession
from tgbot.db.tables import bot_users


class UsersQueries(DbSession):
    async def upsert_user(
        self,
        telegram_user_id: int,
        username: str,
    ) -> ActiveUser:
        """Insert on /start, or refresh username and clear blocked_at on return.

        If the user had finished onboarding and was not paused, is_active is
        set back to true (blocked users can message again after unblock).
        """
        stmt = pg_insert(bot_users).values(
            telegram_user_id=telegram_user_id,
            username=username,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[bot_users.c.telegram_user_id],
            set_={
                "username": stmt.excluded.username,
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
            },
        ).returning(*bot_users.c)

        return active_user_from_row(await self.execute_fetch_exactly_one(stmt))

    async def get_user(self, telegram_user_id: int) -> ActiveUser | None:
        row = await self.fetch_first(
            sa.select(bot_users).where(bot_users.c.telegram_user_id == telegram_user_id)
        )
        return active_user_from_row(row) if row else None

    async def is_admin(self, telegram_user_id: int) -> bool:
        role = await self.fetch_scalar(
            sa.select(bot_users.c.role).where(
                bot_users.c.telegram_user_id == telegram_user_id
            )
        )
        return role == "admin"

    async def get_admin_user_ids(self) -> list[int]:
        """Telegram ids with role=admin (e.g. per-chat bot command scopes)."""
        rows = await self.fetch_scalars(
            sa.select(bot_users.c.telegram_user_id)
            .where(bot_users.c.role == "admin")
            .order_by(bot_users.c.telegram_user_id)
        )
        return [cast(int, user_id) for user_id in rows]

    async def toggle_level(
        self,
        telegram_user_id: int,
        level: CefrLevel,
    ) -> ActiveUser:
        """Add or remove one CEFR level in selected_levels (keyboard toggle)."""
        level_value = sa.literal(level)
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
            )
            .returning(*bot_users.c)
        )

        return active_user_from_row(await self.execute_fetch_exactly_one(stmt))

    async def set_dialect(
        self,
        telegram_user_id: int,
        dialect: DialectPreference,
    ) -> ActiveUser:
        """Save dialect preference and finish onboarding when levels exist.

        is_active becomes true only if levels are set and the user is not
        paused/blocked; otherwise stays inactive.
        """
        has_levels = sa.func.cardinality(bot_users.c.selected_levels) > 0

        stmt = (
            sa.update(bot_users)
            .where(bot_users.c.telegram_user_id == telegram_user_id)
            .values(
                dialect=dialect,
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
            )
            .returning(*bot_users.c)
        )

        return active_user_from_row(await self.execute_fetch_exactly_one(stmt))

    async def clear_blocked_marker(self, telegram_user_id: int) -> None:
        """Clear blocked_at after the user messages again; do not resume schedule."""
        await self.execute(
            sa.update(bot_users)
            .where(
                bot_users.c.telegram_user_id == telegram_user_id,
                bot_users.c.blocked_at.is_not(None),
            )
            .values(blocked_at=None)
        )

    async def set_active(self, telegram_user_id: int, active: bool) -> bool:
        """Pause or resume scheduled delivery for an onboarded user.

        Returns False if the user is missing or has not finished onboarding.
        Resume also clears paused_at and blocked_at.
        """
        values: dict[str, object] = {"is_active": active}
        if active:
            values["paused_at"] = None
            values["blocked_at"] = None
        else:
            values["paused_at"] = sa.func.current_timestamp()

        result = await self.execute(
            sa.update(bot_users)
            .where(
                bot_users.c.telegram_user_id == telegram_user_id,
                bot_users.c.onboarding_completed.is_(True),
            )
            .values(**values)
        )

        return (result.rowcount or 0) > 0

    async def get_active_users(self) -> list[ActiveUser]:
        """Users eligible for the scheduler: active, onboarded, levels + dialect."""
        rows = await self.fetch_all(
            sa.select(bot_users)
            .where(
                bot_users.c.is_active.is_(True),
                bot_users.c.onboarding_completed.is_(True),
                sa.func.cardinality(bot_users.c.selected_levels) > 0,
                bot_users.c.dialect.is_not(None),
            )
            .order_by(bot_users.c.telegram_user_id)
        )

        return [active_user_from_row(row) for row in rows]

    async def deactivate_user(self, telegram_user_id: int) -> None:
        """Mark unreachable (bot blocked): stop delivery and set blocked_at."""
        await self.execute(
            sa.update(bot_users)
            .where(bot_users.c.telegram_user_id == telegram_user_id)
            .values(
                is_active=False,
                blocked_at=sa.func.current_timestamp(),
            )
        )
