"""Admin /word category disambiguation hit."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast


@dataclass(frozen=True)
class WordMatch:
    id: int
    word_us: str
    word_gb: str
    lexical_category: str
    cefr: str


def word_match_from_row(row: object) -> WordMatch:
    data = dict(cast(Mapping[Any, Any], row))
    return WordMatch(
        id=int(data["id"]),
        word_us=str(data["word_us"]),
        word_gb=str(data["word_gb"]),
        lexical_category=str(data["lexical_category"]),
        cefr=str(data["cefr"]),
    )
