"""add oxford_lexical_entries table

Revision ID: c7d8e9f0a1b2
Revises: a1b2c3d4e5f6
Create Date: 2026-08-09 17:00:00.000000

Staging table for Oxford API translation cache imports.
Compatible with databases that already created the table via the old
import_oxford_cache runtime DDL.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS oxford_lexical_entries (
            source_lexical_key TEXT PRIMARY KEY,
            word_us TEXT NOT NULL,
            word_gb TEXT NOT NULL,
            lexical_category TEXT NOT NULL,
            ipa_us TEXT[] NOT NULL,
            ipa_gb TEXT[] NOT NULL,
            definition TEXT NOT NULL DEFAULT '',
            example TEXT NOT NULL DEFAULT '',
            audio_source_us TEXT[] NOT NULL,
            audio_source_gb TEXT[] NOT NULL,
            translations TEXT[] NOT NULL,
            CONSTRAINT oxford_lexical_entries_us_pronunciation_check
                CHECK (cardinality(ipa_us) = cardinality(audio_source_us)),
            CONSTRAINT oxford_lexical_entries_gb_pronunciation_check
                CHECK (cardinality(ipa_gb) = cardinality(audio_source_gb))
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS oxford_lexical_entries_word_us_idx
        ON oxford_lexical_entries (word_us)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS oxford_lexical_entries_word_gb_idx
        ON oxford_lexical_entries (word_gb)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS oxford_lexical_entries_category_idx
        ON oxford_lexical_entries (lexical_category)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS oxford_lexical_entries_translations_idx
        ON oxford_lexical_entries USING GIN (translations)
        """
    )


def downgrade() -> None:
    op.drop_index(
        "oxford_lexical_entries_translations_idx",
        table_name="oxford_lexical_entries",
    )
    op.drop_index(
        "oxford_lexical_entries_category_idx",
        table_name="oxford_lexical_entries",
    )
    op.drop_index(
        "oxford_lexical_entries_word_gb_idx",
        table_name="oxford_lexical_entries",
    )
    op.drop_index(
        "oxford_lexical_entries_word_us_idx",
        table_name="oxford_lexical_entries",
    )
    op.drop_table("oxford_lexical_entries")
