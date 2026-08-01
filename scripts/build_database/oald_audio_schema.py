"""Shared PostgreSQL schema for derived OALD audio representations."""

CREATE_AUDIO_VARIANT_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS oald_audio_variants (
    source_url TEXT NOT NULL
        REFERENCES oald_audio_files(source_url) ON DELETE CASCADE,
    variant_type TEXT NOT NULL,
    source_sha256 CHAR(64) NOT NULL DEFAULT '',
    audio_data BYTEA,
    content_type TEXT NOT NULL DEFAULT '',
    filename TEXT NOT NULL DEFAULT '',
    size_bytes BIGINT,
    sha256 CHAR(64) NOT NULL DEFAULT '',
    conversion_status TEXT NOT NULL DEFAULT 'pending',
    last_error TEXT NOT NULL DEFAULT '',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    converted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (source_url, variant_type),
    CONSTRAINT oald_audio_variant_type_check
        CHECK (variant_type IN ('telegram_voice_opus')),
    CONSTRAINT oald_audio_variant_status_check
        CHECK (conversion_status IN ('pending', 'prepared', 'failed')),
    CONSTRAINT oald_audio_variant_attempt_count_check CHECK (attempt_count >= 0),
    CONSTRAINT oald_audio_variant_size_check
        CHECK (size_bytes IS NULL OR size_bytes >= 0)
)
"""

CREATE_AUDIO_VARIANT_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS oald_audio_variants_status_idx
ON oald_audio_variants (variant_type, conversion_status)
"""

