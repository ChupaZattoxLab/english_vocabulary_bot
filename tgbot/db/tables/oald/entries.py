"""oald_entries table."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from tgbot.db.models.types import CefrLevel
from tgbot.db.tables.base import Base, varchar_enum


class OaldEntry(Base):
    __tablename__ = "oald_entries"  # type: ignore[assignment]
    __table_args__ = (
        sa.Index(
            "oald_entries_word_us_category_idx",
            "word_us",
            "lexical_category",
        ),
        sa.Index(
            "oald_entries_translations_idx",
            "translations",
            postgresql_using="gin",
        ),
        sa.Index(
            "oald_entries_active_idx",
            "is_active",
            "cefr",
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
            name="oald_entries_word_us_check",
        ),
        index=True,
    )

    word_gb: Mapped[str] = mapped_column(
        sa.Text,
        sa.CheckConstraint(
            "btrim(word_gb) <> ''",
            name="oald_entries_word_gb_check",
        ),
        index=True,
    )

    lexical_category: Mapped[str] = mapped_column(
        sa.Text,
        sa.CheckConstraint(
            "btrim(lexical_category) <> ''",
            name="oald_entries_category_check",
        ),
        index=True,
    )

    cefr: Mapped[CefrLevel] = mapped_column(
        varchar_enum(CefrLevel, name="oald_entries_cefr_check"),
        index=True,
    )

    definition_url_oxford: Mapped[str] = mapped_column(
        sa.Text,
        sa.CheckConstraint(
            "btrim(definition_url_oxford) <> ''",
            name="oald_entries_definition_url_check",
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

    is_active: Mapped[bool] = mapped_column(
        sa.Boolean,
        server_default=sa.true(),
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
