"""bot_user_cards table."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from tgbot.db.tables.base import metadata

bot_user_cards = sa.Table(
    "bot_user_cards",
    metadata,
    sa.Column(
        "id",
        sa.BigInteger,
        sa.Identity(always=True),
        primary_key=True,
    ),
    sa.Column(
        "telegram_user_id",
        sa.BigInteger,
        sa.ForeignKey("bot_users.telegram_user_id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "entry_id",
        sa.BigInteger,
        sa.ForeignKey("oald_entries.id"),
        nullable=False,
    ),
    sa.Column("dialect", sa.String(4), nullable=False),
    sa.Column(
        "source_url",
        sa.Text,
        sa.ForeignKey("oald_audio_files.source_url"),
        nullable=False,
    ),
    sa.Column(
        "source_url_gb",
        sa.Text,
        sa.ForeignKey("oald_audio_files.source_url"),
    ),
    sa.Column(
        "scheduled_slot",
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
    ),
    sa.Column(
        "status",
        sa.Text,
        nullable=False,
        server_default=sa.text("'reserved'"),
    ),
    sa.Column("telegram_message_id", sa.BigInteger),
    sa.Column(
        "error_type",
        sa.Text,
        nullable=False,
        server_default=sa.text("''"),
    ),
    sa.Column(
        "error_message",
        sa.Text,
        nullable=False,
        server_default=sa.text("''"),
    ),
    sa.Column(
        "created_at",
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    ),
    sa.Column("delivered_at", postgresql.TIMESTAMP(timezone=True)),
    sa.CheckConstraint(
        "dialect IN ('us', 'gb', 'both')",
        name="bot_user_cards_dialect_check",
    ),
    sa.CheckConstraint(
        "status IN ('reserved', 'delivered', 'failed')",
        name="bot_user_cards_status_check",
    ),
)

sa.Index(
    "bot_user_cards_user_entry_active_uidx",
    bot_user_cards.c.telegram_user_id,
    bot_user_cards.c.entry_id,
    unique=True,
    postgresql_where=sa.text("status IN ('delivered', 'reserved')"),
)
sa.Index(
    "bot_user_cards_user_slot_active_uidx",
    bot_user_cards.c.telegram_user_id,
    bot_user_cards.c.scheduled_slot,
    unique=True,
    postgresql_where=sa.text("status IN ('delivered', 'reserved')"),
)
sa.Index(
    "bot_user_cards_user_status_idx",
    bot_user_cards.c.telegram_user_id,
    bot_user_cards.c.status,
)
sa.Index(
    "bot_user_cards_delivered_at_idx",
    bot_user_cards.c.delivered_at,
)
sa.Index("bot_user_cards_entry_idx", bot_user_cards.c.entry_id)
sa.Index(
    "bot_user_cards_error_idx",
    bot_user_cards.c.status,
    bot_user_cards.c.error_type,
    bot_user_cards.c.created_at,
)
