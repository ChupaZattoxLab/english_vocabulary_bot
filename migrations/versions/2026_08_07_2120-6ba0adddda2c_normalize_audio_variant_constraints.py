"""normalize audio variant constraints

Revision ID: 6ba0adddda2c
Revises: 0bf7b06e17cf
Create Date: 2026-08-07 21:20:27.037070

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '6ba0adddda2c'
down_revision: Union[str, Sequence[str], None] = '0bf7b06e17cf'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'oald_audio_variants'::regclass
                  AND conname = 'oald_audio_variant_attempt_count_check'
            ) THEN
                ALTER TABLE oald_audio_variants
                    ADD CONSTRAINT oald_audio_variant_attempt_count_check
                    CHECK (attempt_count >= 0);
            END IF;

            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'oald_audio_variants'::regclass
                  AND conname = 'oald_audio_variant_size_check'
            ) THEN
                ALTER TABLE oald_audio_variants
                    ADD CONSTRAINT oald_audio_variant_size_check
                    CHECK (size_bytes IS NULL OR size_bytes >= 0);
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        """
        ALTER TABLE oald_audio_variants
            DROP CONSTRAINT IF EXISTS oald_audio_variant_size_check,
            DROP CONSTRAINT IF EXISTS oald_audio_variant_attempt_count_check
        """
    )
