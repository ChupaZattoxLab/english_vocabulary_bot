"""bot_users role, dialect rename, drop unused columns

Revision ID: e1f2a3b4c5d6
Revises: d8e9f0a1b2c3
Create Date: 2026-08-10 00:10:00.000000

Add role for DB-backed admin checks, rename pronunciation → dialect,
and drop unused first_name / updated_at / last_delivery_at columns.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d8e9f0a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "bot_users",
        sa.Column(
            "role",
            sa.Text(),
            server_default=sa.text("'user'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "bot_users_role_check",
        "bot_users",
        "role IN ('user', 'admin')",
    )
    op.create_index("bot_users_role_idx", "bot_users", ["role"])

    op.drop_column("bot_users", "first_name")
    op.drop_column("bot_users", "updated_at")
    op.drop_column("bot_users", "last_delivery_at")

    op.execute(
        "ALTER TABLE bot_users DROP CONSTRAINT IF EXISTS bot_users_pronunciation_check"
    )
    op.alter_column("bot_users", "pronunciation", new_column_name="dialect")
    op.create_check_constraint(
        "bot_users_dialect_check",
        "bot_users",
        "dialect IS NULL OR dialect IN ('us', 'gb', 'both')",
    )


def downgrade() -> None:
    op.drop_constraint("bot_users_dialect_check", "bot_users", type_="check")
    op.alter_column("bot_users", "dialect", new_column_name="pronunciation")
    op.create_check_constraint(
        "bot_users_pronunciation_check",
        "bot_users",
        "pronunciation IS NULL OR pronunciation IN ('us', 'gb', 'both')",
    )

    op.add_column(
        "bot_users",
        sa.Column("last_delivery_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "bot_users",
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
    )
    op.add_column(
        "bot_users",
        sa.Column(
            "first_name",
            sa.Text(),
            server_default=sa.text("''"),
            nullable=False,
        ),
    )

    op.drop_index("bot_users_role_idx", table_name="bot_users")
    op.drop_constraint("bot_users_role_check", "bot_users", type_="check")
    op.drop_column("bot_users", "role")
