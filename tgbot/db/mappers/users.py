"""Map query rows onto user models."""

from __future__ import annotations

from tgbot.db.domain import BotUser
from tgbot.db.mappers.values import (
    as_db_row,
    row_bool,
    row_int,
    row_optional_str,
    row_str,
    row_str_sequence,
)


def user_from_row(row: object) -> BotUser:
    data = as_db_row(row)

    return BotUser(
        telegram_user_id=row_int(data, "telegram_user_id"),
        chat_id=row_int(data, "chat_id"),
        username=row_str(data, "username"),
        first_name=row_str(data, "first_name"),
        selected_levels=row_str_sequence(data, "selected_levels"),
        pronunciation=row_optional_str(data, "pronunciation"),
        onboarding_completed=row_bool(data, "onboarding_completed"),
        is_active=row_bool(data, "is_active"),
    )
