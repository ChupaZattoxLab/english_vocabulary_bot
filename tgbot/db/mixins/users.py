"""User registration, settings, pause/block, and active-user queries."""

from __future__ import annotations

from tgbot.db.mixins.base import PoolBound
from tgbot.db.models import (
    VALID_LEVELS,
    ActiveUser,
    BotUser,
    DatabaseError,
    user_from_row,
)


class UsersMixin(PoolBound):
    async def upsert_user(
        self,
        *,
        telegram_user_id: int,
        chat_id: int,
        username: str,
        first_name: str,
    ) -> BotUser:
        async with self.pool.connection() as connection:
            row = await (
                await connection.execute(
                    """
                    INSERT INTO bot_users (
                        telegram_user_id, chat_id, username, first_name
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (telegram_user_id) DO UPDATE SET
                        chat_id = EXCLUDED.chat_id,
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        blocked_at = NULL,
                        is_active = CASE
                            WHEN bot_users.paused_at IS NULL
                                 AND bot_users.onboarding_completed
                                THEN TRUE
                            ELSE bot_users.is_active
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING *
                    """,
                    (telegram_user_id, chat_id, username, first_name),
                )
            ).fetchone()
        return user_from_row(row)

    async def get_user(self, telegram_user_id: int) -> BotUser | None:
        async with self.pool.connection() as connection:
            row = await (
                await connection.execute(
                    "SELECT * FROM bot_users WHERE telegram_user_id = %s",
                    (telegram_user_id,),
                )
            ).fetchone()
        return user_from_row(row) if row else None

    async def toggle_level(self, telegram_user_id: int, level: str) -> BotUser:
        normalized = level.lower()
        if normalized not in VALID_LEVELS:
            raise ValueError(f"unsupported CEFR level {level!r}")
        async with self.pool.connection() as connection:
            row = await (
                await connection.execute(
                    """
                    UPDATE bot_users
                    SET selected_levels = CASE
                            WHEN %s = ANY(selected_levels)
                                THEN array_remove(selected_levels, %s)
                            ELSE array_append(selected_levels, %s)
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE telegram_user_id = %s
                    RETURNING *
                    """,
                    (normalized, normalized, normalized, telegram_user_id),
                )
            ).fetchone()
        if not row:
            raise DatabaseError("bot user does not exist")
        return user_from_row(row)

    async def set_pronunciation(
        self,
        telegram_user_id: int,
        dialect: str,
    ) -> BotUser:
        normalized = dialect.lower()
        if normalized not in {"us", "gb", "both"}:
            raise ValueError(f"unsupported pronunciation {dialect!r}")
        async with self.pool.connection() as connection:
            row = await (
                await connection.execute(
                    """
                    UPDATE bot_users
                    SET pronunciation = %s,
                        onboarding_completed = cardinality(selected_levels) > 0,
                        is_active = CASE
                            WHEN paused_at IS NOT NULL OR blocked_at IS NOT NULL
                                THEN FALSE
                            ELSE cardinality(selected_levels) > 0
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE telegram_user_id = %s
                    RETURNING *
                    """,
                    (normalized, telegram_user_id),
                )
            ).fetchone()
        if not row:
            raise DatabaseError("bot user does not exist")
        return user_from_row(row)

    async def clear_blocked_marker(self, telegram_user_id: int) -> None:
        """Clear blocked_at after the user messages again; do not resume schedule."""
        async with self.pool.connection() as connection:
            await connection.execute(
                """
                UPDATE bot_users
                SET blocked_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = %s
                  AND blocked_at IS NOT NULL
                """,
                (telegram_user_id,),
            )

    async def set_active(self, telegram_user_id: int, active: bool) -> bool:
        async with self.pool.connection() as connection:
            result = await connection.execute(
                """
                UPDATE bot_users
                SET is_active = %s,
                    paused_at = CASE
                        WHEN %s THEN NULL
                        ELSE CURRENT_TIMESTAMP
                    END,
                    blocked_at = CASE WHEN %s THEN NULL ELSE blocked_at END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = %s
                  AND onboarding_completed
                """,
                (active, active, active, telegram_user_id),
            )
        return result.rowcount > 0

    async def active_users(self) -> list[ActiveUser]:
        async with self.pool.connection() as connection:
            rows = await (
                await connection.execute(
                    """
                    SELECT telegram_user_id, chat_id
                    FROM bot_users
                    WHERE is_active
                      AND onboarding_completed
                      AND cardinality(selected_levels) > 0
                      AND pronunciation IS NOT NULL
                    ORDER BY telegram_user_id
                    """
                )
            ).fetchall()
        return [
            ActiveUser(
                telegram_user_id=int(row["telegram_user_id"]),
                chat_id=int(row["chat_id"]),
            )
            for row in rows
        ]

    async def deactivate_user(self, telegram_user_id: int) -> None:
        async with self.pool.connection() as connection:
            await connection.execute(
                """
                UPDATE bot_users
                SET is_active = FALSE,
                    blocked_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = %s
                """,
                (telegram_user_id,),
            )
