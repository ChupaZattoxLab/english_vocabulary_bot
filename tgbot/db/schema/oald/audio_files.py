"""oald_audio_files table."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from tgbot.db.schema.base import metadata

oald_audio_files = sa.Table(
    "oald_audio_files",
    metadata,
    sa.Column("source_url", sa.Text, primary_key=True),
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
        "download_status",
        sa.Text,
        nullable=False,
        server_default=sa.text("'pending'"),
    ),
    sa.Column("last_http_status", sa.Integer),
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
    sa.Column("last_attempted_at", postgresql.TIMESTAMP(timezone=True)),
    sa.Column("downloaded_at", postgresql.TIMESTAMP(timezone=True)),
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
        "download_status IN ('pending', 'downloaded', 'failed')",
        name="oald_audio_status_check",
    ),
    sa.CheckConstraint(
        "attempt_count >= 0",
        name="oald_audio_attempt_count_check",
    ),
    sa.CheckConstraint(
        "size_bytes IS NULL OR size_bytes >= 0",
        name="oald_audio_size_check",
    ),
)

sa.Index(
    "oald_audio_sha256_idx",
    oald_audio_files.c.sha256,
    postgresql_where=oald_audio_files.c.sha256 != "",
)
