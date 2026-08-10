"""Card domain model behaviour."""

from __future__ import annotations

import pytest

from tests.tgbot.factories import make_card
from tgbot.db.models import Dialect, DialectPreference, card_from_row
from tgbot.db.models.card import ipa_at_position, russian_translation


def test_primary_prefers_us_when_both_present() -> None:
    card = make_card(include_us=True, include_gb=True)
    assert card.primary.dialect == Dialect.US
    assert card.is_both
    assert len(card.variants()) == 2


def test_for_preference_us_drops_gb() -> None:
    card = make_card(include_us=True, include_gb=True)
    view = card.for_preference(DialectPreference.US)
    assert view.us is not None
    assert view.gb is None
    assert not view.is_both


def test_for_preference_requires_requested_variant() -> None:
    card = make_card(include_us=True, include_gb=False)
    with pytest.raises(ValueError, match="no GB"):
        card.for_preference(DialectPreference.GB)


def test_card_without_variants_has_no_primary() -> None:
    card = make_card(include_us=False, include_gb=False)
    with pytest.raises(ValueError, match="no dialect"):
        _ = card.primary


def test_ipa_at_position_uses_matching_index_else_first() -> None:
    assert ipa_at_position(["/a/", "/b/"], 1) == "/b/"
    assert ipa_at_position(["/a/", "/b/"], 99) == "/a/"
    assert ipa_at_position([], 0) == ""
    assert ipa_at_position("not-a-list", 0) == ""


def test_russian_translation_flattens_main_and_also() -> None:
    assert (
        russian_translation({"ru": {"main": "цвет", "also": ["окрас", "цвет"]}})
        == "цвет, окрас"
    )
    assert russian_translation(None) == ""


def test_card_from_row_attaches_dialects_by_preference() -> None:
    row = {
        "entry_id": 7,
        "word_us": "color",
        "word_gb": "colour",
        "lexical_category": "noun",
        "cefr": "b1",
        "definition": "def",
        "example": "ex",
        "translations": {"ru": {"main": "цвет", "also": []}},
        "ipa_us": ["/us/"],
        "ipa_gb": ["/gb/"],
        "us_source_position": 0,
        "gb_source_position": 0,
        "us_source_url": "https://a/us",
        "us_audio_data": b"us",
        "us_content_type": "audio/ogg",
        "us_filename": "us.ogg",
        "gb_source_url": "https://a/gb",
        "gb_audio_data": b"gb",
        "gb_content_type": "audio/ogg",
        "gb_filename": "gb.ogg",
    }
    both = card_from_row(row, DialectPreference.BOTH, user_card_id=3)
    assert both.user_card_id == 3
    assert both.is_both
    assert both.us is not None and both.us.word == "color"
    assert both.gb is not None and both.gb.word == "colour"

    us_only = card_from_row(row, DialectPreference.US)
    assert us_only.us is not None
    assert us_only.gb is None
