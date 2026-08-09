"""oald_audio_variants table."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from tgbot.db.tables.base import metadata

oald_audio_variants = sa.Table(
    "oald_audio_variants",
    metadata,
    sa.Column(
        "source_url",
        sa.Text,
        sa.ForeignKey("oald_audio_files.source_url", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column("variant_type", sa.Text, primary_key=True),
    sa.Column(
        "source_sha256",
        sa.CHAR(64),
        nullable=False,
        server_default=sa.text("''"),
    ),
    sa.Column("audio_data", sa.LargeBinary),
    sa.Column(
        "content_type",
        sa.Text,
        nullable=False,
        server_default=sa.text("''"),
    ),
    sa.Column(
        "filename",
        sa.Text,
        nullable=False,
        server_default=sa.text("''"),
    ),
    sa.Column("size_bytes", sa.BigInteger),
    sa.Column(
        "sha256",
        sa.CHAR(64),
        nullable=False,
        server_default=sa.text("''"),
    ),
    sa.Column(
        "conversion_status",
        sa.Text,
        nullable=False,
        server_default=sa.text("'pending'"),
    ),
    sa.Column(
        "last_error",
        sa.Text,
        nullable=False,
        server_default=sa.text("''"),
    ),
    sa.Column(
        "attempt_count",
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    ),
    sa.Column("converted_at", postgresql.TIMESTAMP(timezone=True)),
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
    sa.CheckConstraint(
        "variant_type IN ('telegram_voice_opus')",
        name="oald_audio_variant_type_check",
    ),
    sa.CheckConstraint(
        "conversion_status IN ('pending', 'prepared', 'failed')",
        name="oald_audio_variant_status_check",
    ),
    sa.CheckConstraint(
        "attempt_count >= 0",
        name="oald_audio_variant_attempt_count_check",
    ),
    sa.CheckConstraint(
        "size_bytes IS NULL OR size_bytes >= 0",
        name="oald_audio_variant_size_check",
    ),
)

sa.Index(
    "oald_audio_variants_status_idx",
    oald_audio_variants.c.variant_type,
    oald_audio_variants.c.conversion_status,
)
