"""bot_users table."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from tgbot.db.schema.base import metadata

bot_users = sa.Table(
    "bot_users",
    metadata,
    sa.Column(
        "telegram_user_id",
        sa.BigInteger,
        primary_key=True,
        autoincrement=False,
    ),
    sa.Column("chat_id", sa.BigInteger, nullable=False),
    sa.Column(
        "username",
        sa.Text,
        nullable=False,
        server_default=sa.text("''"),
    ),
    sa.Column(
        "first_name",
        sa.Text,
        nullable=False,
        server_default=sa.text("''"),
    ),
    sa.Column(
        "selected_levels",
        postgresql.ARRAY(sa.Text),
        nullable=False,
        server_default=sa.text("'{}'::text[]"),
    ),
    sa.Column("pronunciation", sa.String(4)),
    sa.Column(
        "onboarding_completed",
        sa.Boolean,
        nullable=False,
        server_default=sa.false(),
    ),
    sa.Column(
        "is_active",
        sa.Boolean,
        nullable=False,
        server_default=sa.true(),
    ),
    sa.Column(
        "created_at",
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    ),
    sa.Column(
        "updated_at",
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    ),
    sa.Column("last_delivery_at", postgresql.TIMESTAMP(timezone=True)),
    sa.Column("paused_at", postgresql.TIMESTAMP(timezone=True)),
    sa.Column("blocked_at", postgresql.TIMESTAMP(timezone=True)),
    sa.CheckConstraint(
        "pronunciation IS NULL OR pronunciation IN ('us', 'gb', 'both')",
        name="bot_users_pronunciation_check",
    ),
    sa.CheckConstraint(
        "selected_levels <@ ARRAY['a1','a2','b1','b2','c1','c2']::TEXT[]",
        name="bot_users_levels_check",
    ),
)

sa.Index(
    "bot_users_active_idx",
    bot_users.c.is_active,
    bot_users.c.onboarding_completed,
)
