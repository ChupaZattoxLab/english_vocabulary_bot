"""Canonical SQLAlchemy metadata for the PostgreSQL schema.

The bot continues to use psycopg directly at runtime.  This metadata exists so
Alembic has one authoritative schema for migrations and autogeneration.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

metadata = sa.MetaData()


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
        "cefr IN ('a1', 'a2', 'b1', 'b2', 'c1', 'c2')",
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


bot_users = sa.Table(
    "bot_users",
    metadata,
    sa.Column(
        "telegram_user_id",
        sa.BigInteger,
        primary_key=True,
        autoincrement=False,
    ),
    sa.Column("chat_id", sa.BigInteger, nullable=False),
    sa.Column(
        "username",
        sa.Text,
        nullable=False,
        server_default=sa.text("''"),
    ),
    sa.Column(
        "first_name",
        sa.Text,
        nullable=False,
        server_default=sa.text("''"),
    ),
    sa.Column(
        "selected_levels",
        postgresql.ARRAY(sa.Text),
        nullable=False,
        server_default=sa.text("'{}'::text[]"),
    ),
    sa.Column("pronunciation", sa.String(4)),
    sa.Column(
        "onboarding_completed",
        sa.Boolean,
        nullable=False,
        server_default=sa.false(),
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
    sa.Column("last_delivery_at", postgresql.TIMESTAMP(timezone=True)),
    sa.Column("paused_at", postgresql.TIMESTAMP(timezone=True)),
    sa.Column("blocked_at", postgresql.TIMESTAMP(timezone=True)),
    sa.CheckConstraint(
        "pronunciation IS NULL OR pronunciation IN ('us', 'gb', 'both')",
        name="bot_users_pronunciation_check",
    ),
    sa.CheckConstraint(
        "selected_levels <@ ARRAY['a1','a2','b1','b2','c1','c2']::TEXT[]",
        name="bot_users_levels_check",
    ),
)

sa.Index(
    "bot_users_active_idx",
    bot_users.c.is_active,
    bot_users.c.onboarding_completed,
)


bot_user_cards = sa.Table(
    "bot_user_cards",
    metadata,
    sa.Column(
        "id",
        sa.BigInteger,
        sa.Identity(always=True),
        primary_key=True,
    ),
    sa.Column(
        "telegram_user_id",
        sa.BigInteger,
        sa.ForeignKey("bot_users.telegram_user_id", ondelete="CASCADE"),
        nullable=False,
    ),
    sa.Column(
        "entry_id",
        sa.BigInteger,
        sa.ForeignKey("oald_entries.id"),
        nullable=False,
    ),
    sa.Column("dialect", sa.String(4), nullable=False),
    sa.Column(
        "source_url",
        sa.Text,
        sa.ForeignKey("oald_audio_files.source_url"),
        nullable=False,
    ),
    sa.Column(
        "source_url_gb",
        sa.Text,
        sa.ForeignKey("oald_audio_files.source_url"),
    ),
    sa.Column(
        "scheduled_slot",
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
    ),
    sa.Column(
        "status",
        sa.Text,
        nullable=False,
        server_default=sa.text("'reserved'"),
    ),
    sa.Column("telegram_message_id", sa.BigInteger),
    sa.Column(
        "error_type",
        sa.Text,
        nullable=False,
        server_default=sa.text("''"),
    ),
    sa.Column(
        "error_message",
        sa.Text,
        nullable=False,
        server_default=sa.text("''"),
    ),
    sa.Column(
        "created_at",
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    ),
    sa.Column("delivered_at", postgresql.TIMESTAMP(timezone=True)),
    sa.CheckConstraint(
        "dialect IN ('us', 'gb', 'both')",
        name="bot_user_cards_dialect_check",
    ),
    sa.CheckConstraint(
        "status IN ('reserved', 'delivered', 'failed')",
        name="bot_user_cards_status_check",
    ),
)

sa.Index(
    "bot_user_cards_user_entry_active_uidx",
    bot_user_cards.c.telegram_user_id,
    bot_user_cards.c.entry_id,
    unique=True,
    postgresql_where=sa.text("status IN ('delivered', 'reserved')"),
)
sa.Index(
    "bot_user_cards_user_slot_active_uidx",
    bot_user_cards.c.telegram_user_id,
    bot_user_cards.c.scheduled_slot,
    unique=True,
    postgresql_where=sa.text("status IN ('delivered', 'reserved')"),
)
sa.Index(
    "bot_user_cards_user_status_idx",
    bot_user_cards.c.telegram_user_id,
    bot_user_cards.c.status,
)
sa.Index(
    "bot_user_cards_delivered_at_idx",
    bot_user_cards.c.delivered_at,
)
sa.Index("bot_user_cards_entry_idx", bot_user_cards.c.entry_id)
sa.Index(
    "bot_user_cards_error_idx",
    bot_user_cards.c.status,
    bot_user_cards.c.error_type,
    bot_user_cards.c.created_at,
)


bot_scheduler_runs = sa.Table(
    "bot_scheduler_runs",
    metadata,
    sa.Column(
        "scheduled_slot",
        postgresql.TIMESTAMP(timezone=True),
        primary_key=True,
    ),
    sa.Column(
        "status",
        sa.Text,
        nullable=False,
        server_default=sa.text("'running'"),
    ),
    sa.Column(
        "attempted_users",
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    ),
    sa.Column(
        "delivered_cards",
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    ),
    sa.Column(
        "failed_cards",
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    ),
    sa.Column(
        "skipped_users",
        sa.Integer,
        nullable=False,
        server_default=sa.text("0"),
    ),
    sa.Column(
        "started_at",
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    ),
    sa.Column("completed_at", postgresql.TIMESTAMP(timezone=True)),
    sa.Column(
        "error_message",
        sa.Text,
        nullable=False,
        server_default=sa.text("''"),
    ),
    sa.CheckConstraint(
        "status IN ('running', 'completed', 'failed')",
        name="bot_scheduler_runs_status_check",
    ),
)


bot_telegram_audio_cache = sa.Table(
    "bot_telegram_audio_cache",
    metadata,
    sa.Column(
        "source_url",
        sa.Text,
        sa.ForeignKey("oald_audio_files.source_url"),
        primary_key=True,
    ),
    sa.Column("send_method", sa.Text, primary_key=True),
    sa.Column("telegram_file_id", sa.Text, nullable=False),
    sa.Column(
        "updated_at",
        postgresql.TIMESTAMP(timezone=True),
        nullable=False,
        server_default=sa.func.current_timestamp(),
    ),
    sa.CheckConstraint(
        "send_method IN ('voice', 'audio', 'document')",
        name="bot_audio_cache_method_check",
    ),
)


MANAGED_TABLES = frozenset(metadata.tables)
