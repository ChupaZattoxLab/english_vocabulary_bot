"""bot_telegram_audio_cache table."""

from __future__ import annotations

from datetime import datetime
from typing import cast

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from tgbot.db.tables.base import Base, varchar_enum
from tgbot.db.types import TelegramSendMethod


class BotTelegramAudioCache(Base):
    __tablename__ = "bot_telegram_audio_cache"  # type: ignore[assignment]

    source_url: Mapped[str] = mapped_column(
        sa.Text,
        sa.ForeignKey("oald_audio_files.source_url"),
        primary_key=True,
    )

    send_method: Mapped[TelegramSendMethod] = mapped_column(
        varchar_enum(TelegramSendMethod, name="bot_audio_cache_method_check"),
        primary_key=True,
    )

    telegram_file_id: Mapped[str] = mapped_column(sa.Text)

    updated_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        server_default=sa.func.current_timestamp(),
    )


bot_telegram_audio_cache = cast(sa.Table, BotTelegramAudioCache.__table__)
