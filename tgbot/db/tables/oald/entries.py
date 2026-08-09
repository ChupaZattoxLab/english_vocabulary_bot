"""oald_entries table."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from tgbot.db.tables.base import metadata

oald_entries = sa.Table(
    "oald_entries",
    metadata,
    sa.Column(
        "id",
        sa.BigInteger,
        sa.Identity(always=True),
        primary_key=True,
    ),
    sa.Column("word_us", sa.Text, nullable=False),
    sa.Column("word_gb", sa.Text, nullable=False),
    sa.Column("lexical_category", sa.Text, nullable=False),
    sa.Column("cefr", sa.String(2), nullable=False),
    sa.Column("definition_url_oxford", sa.Text, nullable=False, unique=True),
    sa.Column(
        "definition_url_cambridge",
        sa.Text,
        nullable=False,
        server_default=sa.text("''"),
    ),
    sa.Column(
        "ipa_us",
        postgresql.ARRAY(sa.Text),
        nullable=False,
        server_default=sa.text("'{}'::text[]"),
    ),
    sa.Column(
        "ipa_gb",
        postgresql.ARRAY(sa.Text),
        nullable=False,
        server_default=sa.text("'{}'::text[]"),
    ),
    sa.Column("definition", sa.Text, nullable=False),
    sa.Column("example", sa.Text, nullable=False),
    sa.Column(
        "audio_source_us",
        postgresql.ARRAY(sa.Text),
        nullable=False,
        server_default=sa.text("'{}'::text[]"),
    ),
    sa.Column(
        "audio_source_gb",
        postgresql.ARRAY(sa.Text),
        nullable=False,
        server_default=sa.text("'{}'::text[]"),
    ),
    sa.Column(
        "translations",
        postgresql.JSONB,
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    ),
    sa.Column(
        "is_active",
        sa.Boolean,
        nullable=False,
        server_default=sa.true(),
    ),
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
        "cefr IN ('a1', 'a2', 'b1', 'b2', 'c1')",
        name="oald_entries_cefr_check",
    ),
    sa.CheckConstraint(
        "btrim(word_us) <> ''",
        name="oald_entries_word_us_check",
    ),
    sa.CheckConstraint(
        "btrim(word_gb) <> ''",
        name="oald_entries_word_gb_check",
    ),
    sa.CheckConstraint(
        "btrim(lexical_category) <> ''",
        name="oald_entries_category_check",
    ),
    sa.CheckConstraint(
        "btrim(definition_url_oxford) <> ''",
        name="oald_entries_definition_url_check",
    ),
)

sa.Index("oald_entries_word_us_idx", oald_entries.c.word_us)
sa.Index("oald_entries_word_gb_idx", oald_entries.c.word_gb)
sa.Index("oald_entries_category_idx", oald_entries.c.lexical_category)
sa.Index("oald_entries_cefr_idx", oald_entries.c.cefr)
sa.Index(
    "oald_entries_word_us_category_idx",
    oald_entries.c.word_us,
    oald_entries.c.lexical_category,
)
sa.Index(
    "oald_entries_translations_idx",
    oald_entries.c.translations,
    postgresql_using="gin",
)
sa.Index(
    "oald_entries_active_idx",
    oald_entries.c.is_active,
    oald_entries.c.cefr,
)
