"""oald_entry_audio_sources table."""

from __future__ import annotations

from typing import cast

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from tgbot.db.tables.base import Base, varchar_enum
from tgbot.db.types import Dialect


class OaldEntryAudioSource(Base):
    entry_id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.ForeignKey("oald_entries.id", ondelete="CASCADE"),
        primary_key=True,
    )

    dialect: Mapped[Dialect] = mapped_column(
        varchar_enum(Dialect, name="check_oald_entry_audio_dialect"),
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
