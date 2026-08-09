"""Map query rows onto read-model / view dataclasses."""

from __future__ import annotations

from tgbot.db.mappers.values import as_db_row, row_int, row_str
from tgbot.models import WordMatch


def word_match_from_row(row: object) -> WordMatch:
    data = as_db_row(row)

    return WordMatch(
        id=row_int(data, "id"),
        word_us=row_str(data, "word_us"),
        word_gb=row_str(data, "word_gb"),
        lexical_category=row_str(data, "lexical_category"),
        cefr=row_str(data, "cefr"),
    )
