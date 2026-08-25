"""bot_scheduler_runs table."""

from __future__ import annotations

from datetime import datetime
from typing import cast

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from tgbot.db.tables.base import Base, varchar_enum
from tgbot.db.types import SchedulerRunStatus


class BotSchedulerRun(Base):
    scheduled_slot: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        primary_key=True,
    )

    status: Mapped[SchedulerRunStatus] = mapped_column(
        varchar_enum(SchedulerRunStatus, name="check_bot_scheduler_runs_status"),
        server_default=sa.text("'running'"),
    )

    attempted_users: Mapped[int] = mapped_column(
        sa.Integer,
        server_default=sa.text("0"),
    )

    delivered_cards: Mapped[int] = mapped_column(
        sa.Integer,
        server_default=sa.text("0"),
    )

    failed_cards: Mapped[int] = mapped_column(
        sa.Integer,
        server_default=sa.text("0"),
    )

    skipped_users: Mapped[int] = mapped_column(
        sa.Integer,
        server_default=sa.text("0"),
    )

    started_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        server_default=sa.func.current_timestamp(),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
    )

    error_message: Mapped[str] = mapped_column(
        sa.Text,
        server_default=sa.text("''"),
    )


bot_scheduler_runs = cast(sa.Table, BotSchedulerRun.__table__)
