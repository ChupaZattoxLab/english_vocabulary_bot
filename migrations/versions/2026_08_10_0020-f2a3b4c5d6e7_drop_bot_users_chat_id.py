"""drop bot_users.chat_id (private chats only)

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
Create Date: 2026-08-10 02:20:00.000000

Private DMs use telegram_user_id as the send destination; chat_id is redundant.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("bot_users", "chat_id")


def downgrade() -> None:
    op.add_column(
        "bot_users",
        sa.Column("chat_id", sa.BigInteger(), nullable=True),
    )
    op.execute(
        sa.text("UPDATE bot_users SET chat_id = telegram_user_id WHERE chat_id IS NULL")
    )
    op.alter_column("bot_users", "chat_id", nullable=False)
