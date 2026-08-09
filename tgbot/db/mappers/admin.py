"""Map query rows onto admin models."""

from __future__ import annotations

from tgbot.db.domain import AdminUserDetail, AdminWordMatch
from tgbot.db.mappers.values import (
    as_db_row,
    row_bool,
    row_datetime,
    row_int,
    row_optional_datetime,
    row_optional_str,
    row_str,
    row_str_sequence,
)


def admin_user_detail_from_row(row: object) -> AdminUserDetail:
    data = as_db_row(row)

    return AdminUserDetail(
        telegram_user_id=row_int(data, "telegram_user_id"),
        chat_id=row_int(data, "chat_id"),
        username=row_str(data, "username"),
        first_name=row_str(data, "first_name"),
        selected_levels=row_str_sequence(data, "selected_levels"),
        pronunciation=row_optional_str(data, "pronunciation"),
        onboarding_completed=row_bool(data, "onboarding_completed"),
        is_active=row_bool(data, "is_active"),
        created_at=row_datetime(data, "created_at"),
        updated_at=row_datetime(data, "updated_at"),
        last_delivery_at=row_optional_datetime(data, "last_delivery_at"),
        paused_at=row_optional_datetime(data, "paused_at"),
        blocked_at=row_optional_datetime(data, "blocked_at"),
        delivered_cards=row_int(data, "delivered_cards")
        if data["delivered_cards"] is not None
        else 0,
        last_successful_delivery=row_optional_datetime(
            data,
            "last_successful_delivery",
        ),
    )


def admin_word_match_from_row(row: object) -> AdminWordMatch:
    data = as_db_row(row)

    return AdminWordMatch(
        id=row_int(data, "id"),
        word_us=row_str(data, "word_us"),
        word_gb=row_str(data, "word_gb"),
        lexical_category=row_str(data, "lexical_category"),
        cefr=row_str(data, "cefr"),
    )
