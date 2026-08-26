"""oald_entries table."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from tgbot.db.tables.base import Base, varchar_enum
from tgbot.db.types import CefrLevel


class OaldEntry(Base):
    __tablename__ = "oald_entries"  # type: ignore[assignment]
    __table_args__ = (
        sa.Index(
            "ix_oald_entries_word_us_category",
            "word_us",
            "lexical_category",
        ),
        sa.Index(
            "ix_oald_entries_translations",
            "translations",
            postgresql_using="gin",
        ),
    )

    id: Mapped[int] = mapped_column(
        sa.BigInteger,
        sa.Identity(always=True),
        primary_key=True,
    )

    word_us: Mapped[str] = mapped_column(
        sa.Text,
        sa.CheckConstraint(
            "btrim(word_us) <> ''",
            name="check_oald_entries_word_us",
        ),
        index=True,
    )

    word_gb: Mapped[str] = mapped_column(
        sa.Text,
        sa.CheckConstraint(
            "btrim(word_gb) <> ''",
            name="check_oald_entries_word_gb",
        ),
        index=True,
    )

    lexical_category: Mapped[str] = mapped_column(
        sa.Text,
        sa.CheckConstraint(
            "btrim(lexical_category) <> ''",
            name="check_oald_entries_category",
        ),
        index=True,
    )

    cefr: Mapped[CefrLevel] = mapped_column(
        varchar_enum(CefrLevel, name="check_oald_entries_cefr"),
        index=True,
    )

    definition_url_oxford: Mapped[str] = mapped_column(
        sa.Text,
        sa.CheckConstraint(
            "btrim(definition_url_oxford) <> ''",
            name="check_oald_entries_definition_url",
        ),
        unique=True,
    )

    definition_url_cambridge: Mapped[str] = mapped_column(
        sa.Text,
        server_default=sa.text("''"),
    )

    ipa_us: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(sa.Text),
        server_default=sa.text("'{}'::text[]"),
    )

    ipa_gb: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(sa.Text),
        server_default=sa.text("'{}'::text[]"),
    )

    definition: Mapped[str] = mapped_column(sa.Text)

    example: Mapped[str] = mapped_column(sa.Text)

    audio_source_us: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(sa.Text),
        server_default=sa.text("'{}'::text[]"),
    )

    audio_source_gb: Mapped[list[str]] = mapped_column(
        postgresql.ARRAY(sa.Text),
        server_default=sa.text("'{}'::text[]"),
    )

    translations: Mapped[dict[str, Any]] = mapped_column(
        postgresql.JSONB,
        server_default=sa.text("'{}'::jsonb"),
    )

    created_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        server_default=sa.func.current_timestamp(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        postgresql.TIMESTAMP(timezone=True),
        server_default=sa.func.current_timestamp(),
    )


oald_entries = cast(sa.Table, OaldEntry.__table__)
