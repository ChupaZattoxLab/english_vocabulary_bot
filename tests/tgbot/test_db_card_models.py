"""Card domain model behaviour."""

from __future__ import annotations

import uuid

import pytest

from tests.tgbot.factories import make_card, make_variant
from tgbot.db.models import EnglishVariety, EnglishVarietyPreference, card_from_row
from tgbot.db.models.card import (
    choose_cross_variety_pair,
    choose_preference_tracks,
    ipa_at_position,
    russian_translation,
)


def test_primary_prefers_us_when_both_present() -> None:
    card = make_card(include_us=True, include_gb=True)
    assert card.primary.english_variety == EnglishVariety.US
    assert card.is_both
    assert len(card.variants()) == 2


def test_for_preference_us_drops_gb() -> None:
    card = make_card(include_us=True, include_gb=True)
    view = card.for_preference(EnglishVarietyPreference.US)
    assert view.us is not None
    assert view.gb is None
    assert not view.is_both


def test_card_without_variants_has_no_primary() -> None:
    card = make_card(include_us=False, include_gb=False)
    with pytest.raises(ValueError, match="no English variety"):
        _ = card.primary


def test_ipa_at_position_uses_matching_index_else_first() -> None:
    assert ipa_at_position(["/a/", "/b/"], 1) == "/b/"
    assert ipa_at_position(["/a/", "/b/"], 99) == "/a/"
    assert ipa_at_position([], 0) == ""
    assert ipa_at_position("not-a-list", 0) == ""


def test_russian_translation_keeps_importance_order() -> None:
    assert russian_translation(["цвет", "окрас", "цвет"]) == "цвет, окрас"
    assert russian_translation(None) == ""
    assert russian_translation([]) == ""


def test_card_from_row_attaches_english_varieties_by_preference() -> None:
    row = {
        "entry_id": uuid.UUID(int=7),
        "word_us": "color",
        "word_gb": "colour",
        "lexical_category": "noun",
        "cefr": "b1",
        "definition": "def",
        "example": "ex",
        "translations": ["цвет"],
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
    user_card_id = uuid.UUID(int=3)
    both = card_from_row(row, EnglishVarietyPreference.BOTH, user_card_id=user_card_id)
    assert both.user_card_id == user_card_id
    assert both.is_both
    assert both.us is not None and both.us.word == "color"
    assert both.gb is not None and both.gb.word == "colour"

    us_only = card_from_row(row, EnglishVarietyPreference.US)
    assert us_only.us is not None
    assert us_only.gb is None


def test_both_pairs_first_gb_with_a_different_us_ipa() -> None:
    card = make_card(
        include_gb=True,
        us=make_variant(EnglishVariety.US, "color", "/same/"),
        gb=make_variant(EnglishVariety.GB, "colour", "/same/"),
        us_more=(make_variant(EnglishVariety.US, "color", "/other-us/"),),
        gb_more=(make_variant(EnglishVariety.GB, "colour", "/other-gb/"),),
    )

    view = card.for_preference(EnglishVarietyPreference.BOTH)

    assert view.us is not None and view.us.ipa == "/other-us/"
    assert view.gb is not None and view.gb.ipa == "/same/"
    assert view.us_more == ()
    assert view.gb_more == ()
    assert [variant.ipa for variant in view.variants()] == ["/other-us/", "/same/"]


def test_both_keeps_first_tracks_when_every_ipa_matches() -> None:
    assert choose_cross_variety_pair(
        ["/same/", " /same/ "],
        ["/same/", "/same/"],
    ) == (0, 0)
    assert choose_cross_variety_pair([], ["/same/"]) is None


def test_single_variety_sends_only_the_first_track() -> None:
    card = make_card(
        include_gb=True,
        us_more=(make_variant(EnglishVariety.US, "color", "/other/"),),
        gb_more=(make_variant(EnglishVariety.GB, "colour", "/other-gb/"),),
    )

    us_view = card.for_preference(EnglishVarietyPreference.US)
    gb_view = card.for_preference(EnglishVarietyPreference.GB)

    assert [variant.ipa for variant in us_view.variants()] == ["/us/"]
    assert [variant.ipa for variant in gb_view.variants()] == ["/gb/"]


def test_card_from_row_uses_selected_pronunciations() -> None:
    card = card_from_row(
        {
            "entry_id": uuid.UUID(int=7),
            "word_us": "color",
            "word_gb": "colour",
            "lexical_category": "noun",
            "cefr": "b1",
            "ipa_us": ["/ignored/"],
            "us_source_position": 0,
            "us_source_url": "https://a/ignored",
            "us_audio_data": b"ignored",
            "selected_us": [
                {
                    "ipa": "/second/",
                    "source_url": "https://a/two",
                    "audio_data": b"two",
                    "content_type": "audio/ogg",
                    "filename": "two.ogg",
                },
                {
                    "ipa": "/third/",
                    "source_url": "https://a/three",
                    "audio_data": b"three",
                    "content_type": "audio/ogg",
                    "filename": "three.ogg",
                },
            ],
            "selected_gb": [],
        },
        EnglishVarietyPreference.US,
    )

    assert card.gb is None
    assert card.us is not None
    assert card.us.ipa == "/second/"
    assert card.us.audio.source_url == "https://a/two"
    assert card.us.audio.audio_data == b"two"
    assert [variant.ipa for variant in card.variants()] == ["/second/", "/third/"]


def test_both_advances_gb_when_its_ipa_matches_every_us() -> None:
    assert choose_preference_tracks(
        EnglishVarietyPreference.BOTH,
        ["/same/", "/same/"],
        ["/same/", "/other/"],
    ) == (0, 1)
    assert choose_preference_tracks(
        EnglishVarietyPreference.US,
        ["/second/"],
        [],
    ) == (0, None)
    assert choose_preference_tracks(EnglishVarietyPreference.GB, ["/us/"], []) is None


def test_card_from_row_maps_word_search_fields() -> None:
    card = card_from_row(
        {
            "entry_id": uuid.UUID(int=9),
            "word_us": "color",
            "word_gb": "colour",
            "lexical_category": "noun",
            "cefr": "b2",
        }
    )
    assert card.entry_id == uuid.UUID(int=9)
    assert card.word_us == "color"
    assert card.word_gb == "colour"
    assert card.lexical_category == "noun"
    assert card.cefr == "B2"
