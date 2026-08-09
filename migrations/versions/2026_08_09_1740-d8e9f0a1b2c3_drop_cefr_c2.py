"""drop unsupported CEFR level c2

Revision ID: d8e9f0a1b2c3
Revises: c7d8e9f0a1b2
Create Date: 2026-08-09 17:40:00.000000

OALD data only covers A1-C1. Remove C2 from allowed levels and clean
any leftover values before tightening CHECK constraints.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "d8e9f0a1b2c3"
down_revision: Union[str, Sequence[str], None] = "c7d8e9f0a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE bot_users
        SET selected_levels = array_remove(selected_levels, 'c2')
        WHERE selected_levels @> ARRAY['c2']::TEXT[]
        """
    )
    op.execute(
        """
        DELETE FROM bot_user_cards
        WHERE entry_id IN (SELECT id FROM oald_entries WHERE cefr = 'c2')
        """
    )
    op.execute("DELETE FROM oald_entries WHERE cefr = 'c2'")
    op.execute(
        "ALTER TABLE bot_users DROP CONSTRAINT IF EXISTS bot_users_levels_check"
    )
    op.execute(
        """
        ALTER TABLE bot_users
            ADD CONSTRAINT bot_users_levels_check
            CHECK (selected_levels <@ ARRAY['a1','a2','b1','b2','c1']::TEXT[])
        """
    )
    op.execute(
        "ALTER TABLE oald_entries DROP CONSTRAINT IF EXISTS oald_entries_cefr_check"
    )
    op.execute(
        """
        ALTER TABLE oald_entries
            ADD CONSTRAINT oald_entries_cefr_check
            CHECK (cefr IN ('a1', 'a2', 'b1', 'b2', 'c1'))
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE bot_users DROP CONSTRAINT IF EXISTS bot_users_levels_check"
    )
    op.execute(
        """
        ALTER TABLE bot_users
            ADD CONSTRAINT bot_users_levels_check
            CHECK (
                selected_levels <@ ARRAY['a1','a2','b1','b2','c1','c2']::TEXT[]
            )
        """
    )
    op.execute(
        "ALTER TABLE oald_entries DROP CONSTRAINT IF EXISTS oald_entries_cefr_check"
    )
    op.execute(
        """
        ALTER TABLE oald_entries
            ADD CONSTRAINT oald_entries_cefr_check
            CHECK (cefr IN ('a1', 'a2', 'b1', 'b2', 'c1', 'c2'))
        """
    )
