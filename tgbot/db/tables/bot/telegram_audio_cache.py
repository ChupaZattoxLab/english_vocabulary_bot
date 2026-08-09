"""bot_telegram_audio_cache table."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from tgbot.db.tables.base import metadata

bot_telegram_audio_cache = sa.Table(
    "bot_telegram_audio_cache",
    metadata,
    sa.Column(
        "source_url",
        sa.Text,
        sa.ForeignKey("oald_audio_files.source_url"),
        primary_key=True,
    ),
    sa.Column("send_method", sa.Text, primary_key=True),
    sa.Column("telegram_file_id", sa.Text, nullable=False),
    sa.Column(
        "updated_at",
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    ),
    sa.CheckConstraint(
        "send_method IN ('voice', 'audio', 'document')",
        name="bot_audio_cache_method_check",
    ),
)
