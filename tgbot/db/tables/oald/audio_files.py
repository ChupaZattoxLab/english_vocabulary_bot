"""oald_audio_files table."""

from __future__ import annotations

from datetime import datetime
from typing import cast

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from tgbot.db.tables.base import Base, varchar_enum
from tgbot.db.types import AudioDownloadStatus


class OaldAudioFile(Base):
    __table_args__ = (
        sa.Index(
            "ix_oald_audio_sha256",
            "sha256",
            postgresql_where=sa.text("sha256 != ''"),
        ),
    )

    source_url: Mapped[str] = mapped_column(sa.Text, primary_key=True)

    audio_data: Mapped[bytes | None] = mapped_column(sa.LargeBinary)

    content_type: Mapped[str] = mapped_column(
        sa.Text,
        server_default=sa.text("''"),
    )

    filename: Mapped[str] = mapped_column(
        sa.Text,
        server_default=sa.text("''"),
    )

    size_bytes: Mapped[int | None] = mapped_column(
        sa.BigInteger,
        sa.CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name="check_oald_audio_size",
        ),
    )

    sha256: Mapped[str] = mapped_column(
        sa.CHAR(64),
        server_default=sa.text("''"),
    )

    download_status: Mapped[AudioDownloadStatus] = mapped_column(
        varchar_enum(AudioDownloadStatus, name="check_oald_audio_status"),
        server_default=sa.text("'pending'"),
    )

    last_http_status: Mapped[int | None] = mapped_column(sa.Integer)

    last_error: Mapped[str] = mapped_column(
        sa.Text,
        server_default=sa.text("''"),
    )

    attempt_count: Mapped[int] = mapped_column(
        sa.Integer,
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="check_oald_audio_attempt_count",
        ),
        server_default=sa.text("0"),
    )

    last_attempted_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
    )

    downloaded_at: Mapped[datetime | None] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
    )

    created_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        server_default=sa.func.current_timestamp(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        server_default=sa.func.current_timestamp(),
    )


oald_audio_files = cast(sa.Table, OaldAudioFile.__table__)
