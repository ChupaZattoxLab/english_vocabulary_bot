"""partial unique indexes for bot_user_cards

Revision ID: a1b2c3d4e5f6
Revises: 6ba0adddda2c
Create Date: 2026-08-08 20:27:00.000000

Failed delivery rows must not block retrying the same word or schedule slot.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "6ba0adddda2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE_STATUSES = "status IN ('delivered', 'reserved')"


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE bot_user_cards
            DROP CONSTRAINT IF EXISTS bot_user_cards_telegram_user_id_entry_id_key
        """
    )
    op.execute(
        """
        ALTER TABLE bot_user_cards
            DROP CONSTRAINT IF EXISTS bot_user_cards_telegram_user_id_scheduled_slot_key
        """
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS bot_user_cards_user_entry_active_uidx
        ON bot_user_cards (telegram_user_id, entry_id)
        WHERE {_ACTIVE_STATUSES}
        """
    )
    op.execute(
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS bot_user_cards_user_slot_active_uidx
        ON bot_user_cards (telegram_user_id, scheduled_slot)
        WHERE {_ACTIVE_STATUSES}
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS bot_user_cards_user_slot_active_uidx")
    op.execute("DROP INDEX IF EXISTS bot_user_cards_user_entry_active_uidx")
    op.create_unique_constraint(
        "bot_user_cards_telegram_user_id_entry_id_key",
        "bot_user_cards",
        ["telegram_user_id", "entry_id"],
    )
    op.create_unique_constraint(
        "bot_user_cards_telegram_user_id_scheduled_slot_key",
        "bot_user_cards",
        ["telegram_user_id", "scheduled_slot"],
    )
