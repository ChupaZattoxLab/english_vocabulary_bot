"""bot_user_cards table."""

from __future__ import annotations

from datetime import datetime
from typing import cast

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from tgbot.db.tables.base import Base, varchar_enum
from tgbot.db.types import CardStatus, DialectPreference


class BotUserCard(Base):
    __table_args__ = (
        sa.Index(
            "uix_bot_user_cards_user_entry_active",
            "telegram_user_id",
            "entry_id",
            unique=True,
            postgresql_where=sa.text("status IN ('delivered', 'reserved')"),
        ),
        sa.Index(
            "uix_bot_user_cards_user_slot_active",
            "telegram_user_id",
            "scheduled_slot",
            unique=True,
            postgresql_where=sa.text("status IN ('delivered', 'reserved')"),
        ),
        sa.Index(
            "ix_bot_user_cards_user_status",
            "telegram_user_id",
            "status",
        ),
        sa.Index(
            "ix_bot_user_cards_error",
            "status",
            "error_type",
            "created_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.Identity(always=True),
        primary_key=True,
    )

    telegram_user_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("bot_users.telegram_user_id", ondelete="CASCADE"),
    )

    entry_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("oald_entries.id"),
        index=True,
    )

    dialect: Mapped[DialectPreference] = mapped_column(
        varchar_enum(DialectPreference, name="check_bot_user_cards_dialect"),
    )

    source_url: Mapped[str] = mapped_column(
        sa.Text,
        sa.ForeignKey("oald_audio_files.source_url"),
    )

    source_url_gb: Mapped[str | None] = mapped_column(
        sa.Text,
        sa.ForeignKey("oald_audio_files.source_url"),
    )

    scheduled_slot: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
    )

    status: Mapped[CardStatus] = mapped_column(
        varchar_enum(CardStatus, name="check_bot_user_cards_status"),
        server_default=sa.text("'reserved'"),
    )

    telegram_message_id: Mapped[int | None] = mapped_column(sa.BigInteger)

    error_type: Mapped[str] = mapped_column(
        sa.Text,
        server_default=sa.text("''"),
    )

    error_message: Mapped[str] = mapped_column(
        sa.Text,
        server_default=sa.text("''"),
    )

    created_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        server_default=sa.func.current_timestamp(),
    )

    delivered_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        index=True,
    )


bot_user_cards = cast(sa.Table, BotUserCard.__table__)
