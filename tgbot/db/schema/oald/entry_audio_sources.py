"""oald_entry_audio_sources table."""

from __future__ import annotations

import sqlalchemy as sa

from tgbot.db.schema.base import metadata

oald_entry_audio_sources = sa.Table(
    "oald_entry_audio_sources",
    metadata,
    sa.Column(
        "entry_id",
        sa.BigInteger,
        sa.ForeignKey("oald_entries.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    sa.Column("dialect", sa.String(2), primary_key=True),
    sa.Column("source_position", sa.Integer, primary_key=True),
    sa.Column(
        "source_url",
        sa.Text,
        sa.ForeignKey("oald_audio_files.source_url"),
        nullable=False,
    ),
    sa.CheckConstraint(
        "dialect IN ('us', 'gb')",
        name="oald_entry_audio_dialect_check",
    ),
    sa.CheckConstraint(
        "source_position >= 0",
        name="oald_entry_audio_position_check",
    ),
)

sa.Index(
    "oald_entry_audio_source_url_idx",
    oald_entry_audio_sources.c.source_url,
)
sa.Index(
    "oald_entry_audio_dialect_idx",
    oald_entry_audio_sources.c.dialect,
)
