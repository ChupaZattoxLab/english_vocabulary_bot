"""bot_scheduler_runs table."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from tgbot.db.tables.base import metadata

bot_scheduler_runs = sa.Table(
    "bot_scheduler_runs",
    metadata,
    sa.Column(
        "scheduled_slot",
        postgresql.TIMESTAMP(timezone=True),
        primary_key=True,
    ),
    sa.Column(
        "status",
        sa.Text,
        nullable=False,
        server_default=sa.text("'running'"),
    ),
    sa.Column(
        "attempted_users",
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    ),
    sa.Column(
        "delivered_cards",
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    ),
    sa.Column(
        "failed_cards",
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    ),
    sa.Column(
        "skipped_users",
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    ),
    sa.Column(
        "started_at",
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    ),
    sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True)),
    sa.Column(
        "error_message",
        sa.Text,
        nullable=False,
        server_default=sa.text("''"),
    ),
    sa.CheckConstraint(
        "status IN ('running', 'completed', 'failed')",
        name="bot_scheduler_runs_status_check",
    ),
)
