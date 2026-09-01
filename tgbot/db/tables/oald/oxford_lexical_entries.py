"""oxford_lexical_entries table (Oxford API cache staging)."""

from __future__ import annotations

from typing import cast

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from tgbot.db.tables.base import Base


class OxfordLexicalEntry(Base):
    __tablename__ = "oxford_lexical_entries"  # type: ignore[assignment]
    __table_args__ = (
        sa.CheckConstraint(
            "cardinality(ipa_us) = cardinality(audio_source_us)",
            name="check_oxford_lexical_entries_us_pronunciation",
        ),
        sa.CheckConstraint(
            "cardinality(ipa_gb) = cardinality(audio_source_gb)",
            name="check_oxford_lexical_entries_gb_pronunciation",
        ),
        sa.Index(
            "ix_oxford_lexical_entries_translations",
            "translations",
            postgresql_using="gin",
        ),
    )

    source_lexical_key: Mapped[str] = mapped_column(sa.Text, primary_key=True)

    word_us: Mapped[str] = mapped_column(sa.Text, index=True)

    word_gb: Mapped[str] = mapped_column(sa.Text, index=True)

    lexical_category: Mapped[str] = mapped_column(sa.Text, index=True)

    ipa_us: Mapped[list[str]] = mapped_column(postgresql.ARRAY(sa.Text))

    ipa_gb: Mapped[list[str]] = mapped_column(postgresql.ARRAY(sa.Text))

    definition: Mapped[str] = mapped_column(
        sa.Text,
        server_default=sa.text("''"),
    )

    example: Mapped[str] = mapped_column(
        sa.Text,
        server_default=sa.text("''"),
    )

    audio_source_us: Mapped[list[str]] = mapped_column(postgresql.ARRAY(sa.Text))

    audio_source_gb: Mapped[list[str]] = mapped_column(postgresql.ARRAY(sa.Text))

    translations: Mapped[list[str]] = mapped_column(postgresql.ARRAY(sa.Text))


oxford_lexical_entries = cast(sa.Table, OxfordLexicalEntry.__table__)
