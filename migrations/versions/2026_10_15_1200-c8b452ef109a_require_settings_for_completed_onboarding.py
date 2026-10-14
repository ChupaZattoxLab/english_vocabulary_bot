"""Require levels and an English variety for completed onboarding.

Revision ID: c8b452ef109a
Revises: a60af6cd5168
"""

from alembic import op

revision = "c8b452ef109a"
down_revision = "a60af6cd5168"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE bot_users SET onboarding_completed = FALSE, is_active = FALSE "
        "WHERE onboarding_completed AND "
        "(cardinality(selected_levels) = 0 OR english_variety IS NULL)"
    )
    op.create_check_constraint(
        "check_bot_users_onboarding_settings",
        "bot_users",
        "NOT onboarding_completed OR "
        "(cardinality(selected_levels) > 0 AND english_variety IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "check_bot_users_onboarding_settings", "bot_users", type_="check"
    )
    # Repaired user states cannot be reconstructed safely.
