"""oald_entry_audio_sources table."""

from __future__ import annotations

import uuid
from typing import cast

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from tgbot.db.tables.base import Base, varchar_enum
from tgbot.db.types import EnglishVariety


class OaldEntryAudioSource(Base):
    entry_id: Mapped[uuid.UUID] = mapped_column(
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("oald_entries.id", ondelete="CASCADE"),
        primary_key=True,
    )

    english_variety: Mapped[EnglishVariety] = mapped_column(
        varchar_enum(EnglishVariety, name="check_oald_entry_audio_english_variety"),
        primary_key=True,
        index=True,
    )

    source_position: Mapped[int] = mapped_column(
        sa.Integer,
        sa.CheckConstraint(
            "source_position >= 0",
            name="check_oald_entry_audio_position",
        ),
        primary_key=True,
    )

    source_url: Mapped[str] = mapped_column(
        sa.Text,
        sa.ForeignKey("oald_audio_files.source_url"),
        index=True,
    )


oald_entry_audio_sources = cast(sa.Table, OaldEntryAudioSource.__table__)
