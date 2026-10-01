"""oald_audio_variants table."""

from __future__ import annotations

from datetime import datetime
from typing import cast

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from tgbot.db.tables.base import Base, varchar_enum
from tgbot.db.types import AudioConversionStatus, AudioVariantType


class OaldAudioVariant(Base):
    __table_args__ = (
        sa.Index(
            "ix_oald_audio_variants_status",
            "variant_type",
            "conversion_status",
        ),
    )

    source_url: Mapped[str] = mapped_column(
        sa.Text,
        sa.ForeignKey("oald_audio_files.source_url", ondelete="CASCADE"),
        primary_key=True,
    )

    variant_type: Mapped[AudioVariantType] = mapped_column(
        varchar_enum(AudioVariantType, name="check_oald_audio_variants_type"),
        primary_key=True,
    )

    source_sha256: Mapped[str] = mapped_column(
        sa.CHAR(64),
        server_default=sa.text("''"),
    )

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
            name="check_oald_audio_variants_size",
        ),
    )

    sha256: Mapped[str] = mapped_column(
        sa.CHAR(64),
        server_default=sa.text("''"),
    )

    conversion_status: Mapped[AudioConversionStatus] = mapped_column(
        varchar_enum(
            AudioConversionStatus,
            name="check_oald_audio_variants_status",
        ),
        server_default=sa.text("'pending'"),
    )

    last_error: Mapped[str] = mapped_column(
        sa.Text,
        server_default=sa.text("''"),
    )

    attempt_count: Mapped[int] = mapped_column(
        sa.Integer,
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="check_oald_audio_variants_attempt_count",
        ),
        server_default=sa.text("0"),
    )

    converted_at: Mapped[datetime | None] = mapped_column(
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


oald_audio_variants = cast(sa.Table, OaldAudioVariant.__table__)
