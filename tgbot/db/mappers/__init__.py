"""Map SQLAlchemy/psycopg row mappings onto domain dataclasses."""

from tgbot.db.mappers.admin import admin_user_detail_from_row, admin_word_match_from_row
from tgbot.db.mappers.cards import card_from_row, selected_ipa, translation_text
from tgbot.db.mappers.users import user_from_row
from tgbot.db.mappers.values import (
    as_db_row,
    as_db_rows,
    row_bool,
    row_bytes,
    row_datetime,
    row_int,
    row_optional_datetime,
    row_optional_str,
    row_str,
    row_str_sequence,
)

__all__ = [
    "admin_user_detail_from_row",
    "admin_word_match_from_row",
    "as_db_row",
    "as_db_rows",
    "card_from_row",
    "row_bool",
    "row_bytes",
    "row_datetime",
    "row_int",
    "row_optional_datetime",
    "row_optional_str",
    "row_str",
    "row_str_sequence",
    "selected_ipa",
    "translation_text",
    "user_from_row",
]
