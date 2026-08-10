"""bot_users table."""

from __future__ import annotations

from datetime import datetime
from typing import cast

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from tgbot.db.models.types import DialectPreference, UserRole
from tgbot.db.tables.base import Base, varchar_enum


class BotUser(Base):
    __table_args__ = (
        sa.Index(
            "bot_users_active_idx",
            "is_active",
            "onboarding_completed",
        ),
    )

    telegram_user_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        primary_key=True,
        autoincrement=False,
    )

    username: Mapped[str] = mapped_column(
        sa.Text,
        server_default=sa.text("''"),
    )

    role: Mapped[UserRole] = mapped_column(
        varchar_enum(UserRole, name="bot_users_role_check"),
        server_default=sa.text("'user'"),
        index=True,
    )

    selected_levels: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(sa.Text),
        sa.CheckConstraint(
            "selected_levels <@ ARRAY['a1','a2','b1','b2','c1']::TEXT[]",
            name="bot_users_levels_check",
        ),
        server_default=sa.text("'{}'::text[]"),
    )

    dialect: Mapped[DialectPreference | None] = mapped_column(
        varchar_enum(DialectPreference, name="bot_users_dialect_check"),
    )

    onboarding_completed: Mapped[bool] = mapped_column(
        sa.Boolean,
        server_default=sa.false(),
    )

    is_active: Mapped[bool] = mapped_column(
        sa.Boolean,
        server_default=sa.true(),
    )

    created_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        server_default=sa.func.current_timestamp(),
    )

    paused_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
    )

    blocked_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
    )


bot_users = cast(sa.Table, BotUser.__table__)
