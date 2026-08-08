"""partial unique indexes for bot_user_cards

Revision ID: a1b2c3d4e5f6
Revises: 6ba0adddda2c
Create Date: 2026-08-08 20:27:00.000000

Failed delivery rows must not block retrying the same word or schedule slot.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "6ba0adddda2c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ACTIVE_STATUSES = "status IN ('delivered', 'reserved')"


def upgrade() -> None:
    op.drop_constraint(
        "bot_user_cards_telegram_user_id_entry_id_key",
        "bot_user_cards",
        type_="unique",
    )
    op.drop_constraint(
        "bot_user_cards_telegram_user_id_scheduled_slot_key",
        "bot_user_cards",
        type_="unique",
    )
    op.create_index(
        "bot_user_cards_user_entry_active_uidx",
        "bot_user_cards",
        ["telegram_user_id", "entry_id"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE_STATUSES),
    )
    op.create_index(
        "bot_user_cards_user_slot_active_uidx",
        "bot_user_cards",
        ["telegram_user_id", "scheduled_slot"],
        unique=True,
        postgresql_where=sa.text(_ACTIVE_STATUSES),
    )


def downgrade() -> None:
    op.drop_index("bot_user_cards_user_slot_active_uidx", table_name="bot_user_cards")
    op.drop_index("bot_user_cards_user_entry_active_uidx", table_name="bot_user_cards")
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
