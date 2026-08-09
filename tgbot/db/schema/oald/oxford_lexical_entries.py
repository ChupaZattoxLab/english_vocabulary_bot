"""oxford_lexical_entries table (Oxford API cache staging)."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from tgbot.db.schema.base import metadata

oxford_lexical_entries = sa.Table(
    "oxford_lexical_entries",
    metadata,
    sa.Column("source_lexical_key", sa.Text, primary_key=True),
    sa.Column("word_us", sa.Text, nullable=False),
    sa.Column("word_gb", sa.Text, nullable=False),
    sa.Column("lexical_category", sa.Text, nullable=False),
    sa.Column("ipa_us", postgresql.ARRAY(sa.Text), nullable=False),
    sa.Column("ipa_gb", postgresql.ARRAY(sa.Text), nullable=False),
    sa.Column(
        "definition",
        sa.Text,
        nullable=False,
        server_default=sa.text("''"),
    ),
    sa.Column(
        "example",
        sa.Text,
        nullable=False,
        server_default=sa.text("''"),
    ),
    sa.Column("audio_source_us", postgresql.ARRAY(sa.Text), nullable=False),
    sa.Column("audio_source_gb", postgresql.ARRAY(sa.Text), nullable=False),
    sa.Column("translations", postgresql.ARRAY(sa.Text), nullable=False),
    sa.CheckConstraint(
        "cardinality(ipa_us) = cardinality(audio_source_us)",
        name="oxford_lexical_entries_us_pronunciation_check",
    ),
    sa.CheckConstraint(
        "cardinality(ipa_gb) = cardinality(audio_source_gb)",
        name="oxford_lexical_entries_gb_pronunciation_check",
    ),
)

sa.Index("oxford_lexical_entries_word_us_idx", oxford_lexical_entries.c.word_us)
sa.Index("oxford_lexical_entries_word_gb_idx", oxford_lexical_entries.c.word_gb)
sa.Index(
    "oxford_lexical_entries_category_idx",
    oxford_lexical_entries.c.lexical_category,
)
sa.Index(
    "oxford_lexical_entries_translations_idx",
    oxford_lexical_entries.c.translations,
    postgresql_using="gin",
)
