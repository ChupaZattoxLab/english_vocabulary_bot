"""Parse Oxford API cache files and build import rows."""

from __future__ import annotations

import json
import logging
import unicodedata
from collections import Counter, defaultdict
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import quote

from scripts.oald.oxford_import.models import (
    DatasetDefinition,
    OxfordCacheError,
    OxfordGroup,
    OxfordRow,
)
from tgbot.db.models import Dialect

LOGGER = logging.getLogger("tgbot.oxford_import")

US_REGION_MARKERS = {
    "american",
    "american english",
    "general american",
    "united states",
    "us",
    "usa",
}
GB_REGION_MARKERS = {
    "british",
    "british english",
    "gb",
    "great britain",
    "uk",
    "united kingdom",
}

DATASET_POS_BY_OXFORD_CATEGORY: dict[str, set[str]] = {
    "noun": {"noun"},
    "verb": {"verb", "modal verb", "auxiliary verb", "linking verb"},
    "adjective": {"adjective"},
    "adverb": {"adverb"},
    "preposition": {"preposition"},
    "conjunction": {"conjunction"},
    "pronoun": {"pronoun"},
    "determiner": {"determiner"},
    "article": {"indefinite article", "definite article"},
    "interjection": {"exclamation", "interjection"},
    "number": {"number", "ordinal number"},
    "numeral": {"number", "ordinal number"},
    "other": {"infinitive marker"},
}


def parse_cache_files(
    source_dir: Path,
    limit_files: int | None = None,
    strict: bool = False,
) -> tuple[dict[str, OxfordGroup], Counter[str]]:
    groups: dict[str, OxfordGroup] = {}
    stats: Counter[str] = Counter()
    paths = sorted(source_dir.glob("*.json"), key=lambda path: path.name.lower())
    if limit_files is not None:
        paths = paths[:limit_files]

    for path in paths:
        stats["files_seen"] += 1
        try:
            wrapper = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            stats["invalid_files"] += 1
            message = f"Could not parse {path}: {exc}"
            if strict:
                raise OxfordCacheError(message) from exc
            LOGGER.error(message)
            continue

        status = wrapper.get("status")
        if status == 404:
            stats["not_found_files"] += 1
            continue
        if wrapper.get("ok") is not True or status != 200:
            stats["skipped_status_files"] += 1
            LOGGER.warning("Skipping %s with Oxford status %r", path.name, status)
            continue

        stats["successful_files"] += 1
        data = wrapper.get("data") or {}
        for result in data.get("results") or []:
            result_id = normalize_word(
                result.get("id")
                or result.get("word")
                or wrapper.get("resolved")
                or wrapper.get("query")
            )
            if not result_id:
                stats["invalid_results"] += 1
                LOGGER.warning("Skipping result without an ID in %s", path.name)
                continue

            for lexical_entry in result.get("lexicalEntries") or []:
                category_data = lexical_entry.get("lexicalCategory") or {}
                lexical_category = normalize_category(
                    category_data.get("id") or category_data.get("text")
                )
                if not lexical_category:
                    stats["invalid_lexical_entries"] += 1
                    LOGGER.warning(
                        "Skipping lexical entry without a category in %s", path.name
                    )
                    continue
                key = source_key(result_id, lexical_category)
                group = groups.setdefault(
                    key,
                    OxfordGroup(
                        source_lexical_key=key,
                        lexical_category=lexical_category,
                    ),
                )
                if not lexical_entry.get("text"):
                    append_unique(group.base_words, result_id)
                process_lexical_entry(group, lexical_entry)

    stats["groups"] = len(groups)
    stats["multi_entry_groups"] = sum(
        group.entry_count > 1 for group in groups.values()
    )
    return groups, stats


def load_definition_index(
    words_json: Path,
) -> dict[tuple[str, str], list[DatasetDefinition]]:
    try:
        raw_rows = json.loads(words_json.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OxfordCacheError(
            f"Could not read definitions from {words_json}: {exc}"
        ) from exc
    if not isinstance(raw_rows, list):
        raise OxfordCacheError(
            f"Definitions file must contain a JSON array: {words_json}"
        )

    index: dict[tuple[str, str], list[DatasetDefinition]] = defaultdict(list)
    for ordinal, raw in enumerate(raw_rows):
        word = normalize_word(raw.get("word"))
        part_of_speech = normalize_category(raw.get("pos"))
        if not word or not part_of_speech:
            continue
        item = DatasetDefinition(
            ordinal=ordinal,
            word=word,
            part_of_speech=part_of_speech,
            phonetic=normalize_ipa(raw.get("phonetic")),
            definition=str(raw.get("definition") or "").strip(),
            example=str(raw.get("example") or "").strip(),
        )
        index[(word, part_of_speech)].append(item)
    return index


def build_rows(
    groups: Mapping[str, OxfordGroup],
    definition_index: Mapping[tuple[str, str], list[DatasetDefinition]],
) -> tuple[list[OxfordRow], Counter[str]]:
    rows: list[OxfordRow] = []
    stats: Counter[str] = Counter()
    for key in sorted(groups):
        group = groups[key]
        word_us, word_gb = group_spellings(group)
        if not word_us or not word_gb:
            stats["missing_spelling"] += 1
            LOGGER.warning("Skipping %s because its spelling is missing", key)
            continue
        definition, example, match_status = choose_definition(group, definition_index)
        stats[f"definition_{match_status}"] += 1

        ipa_us = [ipa for ipa, _ in group.pronunciations_us]
        audio_us = [audio for _, audio in group.pronunciations_us]
        ipa_gb = [ipa for ipa, _ in group.pronunciations_gb]
        audio_gb = [audio for _, audio in group.pronunciations_gb]
        rows.append(
            OxfordRow(
                source_lexical_key=key,
                word_us=word_us,
                word_gb=word_gb,
                lexical_category=group.lexical_category,
                ipa_us=ipa_us,
                ipa_gb=ipa_gb,
                definition=definition,
                example=example,
                audio_source_us=audio_us,
                audio_source_gb=audio_gb,
                translations=list(group.translations),
            )
        )
        if group.translations:
            stats["with_translations"] += 1
        else:
            stats["without_translations"] += 1
    stats["rows"] = len(rows)
    return rows, stats


def log_summary(file_stats: Counter[str], row_stats: Counter[str]) -> None:
    LOGGER.info(
        "Oxford cache: files=%s, successful=%s, 404=%s, invalid=%s, "
        "groups=%s, multi_entry_groups=%s",
        file_stats["files_seen"],
        file_stats["successful_files"],
        file_stats["not_found_files"],
        file_stats["invalid_files"],
        file_stats["groups"],
        file_stats["multi_entry_groups"],
    )
    LOGGER.info(
        "Output rows=%s, with_translations=%s, without_translations=%s, "
        "definitions(unique=%s, phonetic=%s, ambiguous=%s, missing=%s)",
        row_stats["rows"],
        row_stats["with_translations"],
        row_stats["without_translations"],
        row_stats["definition_unique_word_pos"],
        row_stats["definition_phonetic"],
        row_stats["definition_ambiguous"],
        row_stats["definition_missing"],
    )


def process_lexical_entry(
    group: OxfordGroup,
    lexical_entry: Mapping[str, Any],
) -> None:
    base_word = normalize_word(lexical_entry.get("text"))
    if base_word:
        append_unique(group.base_words, base_word)

    for pronunciation in lexical_entry.get("pronunciations") or []:
        add_pronunciation(group, pronunciation)
    for variant in lexical_entry.get("variantForms") or []:
        process_variant_form(group, variant)

    for entry in lexical_entry.get("entries") or []:
        group.entry_count += 1
        for pronunciation in entry.get("pronunciations") or []:
            add_pronunciation(group, pronunciation)
        for variant in entry.get("variantForms") or []:
            process_variant_form(group, variant)
        add_translations(group, entry.get("senses") or [])


def process_variant_form(group: OxfordGroup, variant: Mapping[str, Any]) -> None:
    regions = regions_from_items(variant.get("regions") or [])
    variant_word = normalize_word(variant.get("text"))
    if variant_word:
        if Dialect.US in regions:
            append_unique(group.us_variants, variant_word)
        if Dialect.GB in regions:
            append_unique(group.gb_variants, variant_word)
    for pronunciation in variant.get("pronunciations") or []:
        add_pronunciation(group, pronunciation, inherited_regions=regions)


def add_translations(group: OxfordGroup, senses: Iterable[Mapping[str, Any]]) -> None:
    for sense in iter_senses(senses):
        for translation in sense.get("translations") or []:
            language = normalize_word(translation.get("language"))
            if language not in {"", "ru", "russian"}:
                continue
            text = unicodedata.normalize(
                "NFC", str(translation.get("text") or "").strip()
            )
            if text:
                append_unique(group.translations, text)


def add_pronunciation(
    group: OxfordGroup,
    pronunciation: Mapping[str, Any],
    inherited_regions: set[Dialect] | None = None,
) -> None:
    notation = normalize_word(pronunciation.get("phoneticNotation"))
    raw_ipa = pronunciation.get("phoneticSpelling")
    ipa = normalize_ipa(raw_ipa) if not notation or notation == "ipa" else ""
    audio = str(pronunciation.get("audioFile") or "").strip()
    if not ipa and not audio:
        return

    regions = regions_from_items(pronunciation.get("dialects") or [])
    if not regions:
        regions = set(inherited_regions or ())
    pair = (ipa, audio)
    if Dialect.US in regions:
        append_unique(group.pronunciations_us, pair)
    if Dialect.GB in regions:
        append_unique(group.pronunciations_gb, pair)


def choose_definition(
    group: OxfordGroup,
    definition_index: Mapping[tuple[str, str], list[DatasetDefinition]],
) -> tuple[str, str, str]:
    candidates = definition_candidates(group, definition_index)
    if not candidates:
        return "", "", "missing"
    if len(candidates) == 1:
        candidate = candidates[0]
        return candidate.definition, candidate.example, "unique_word_pos"

    group_ipas = {
        comparable_ipa(ipa)
        for ipa, _ in [*group.pronunciations_us, *group.pronunciations_gb]
        if ipa
    }
    phonetic_matches = [
        candidate
        for candidate in candidates
        if comparable_ipa(candidate.phonetic) in group_ipas
    ]
    if len(phonetic_matches) == 1:
        candidate = phonetic_matches[0]
        return candidate.definition, candidate.example, "phonetic"

    LOGGER.warning(
        "Ambiguous definition for %s: %s dataset candidates, %s phonetic matches",
        group.source_lexical_key,
        len(candidates),
        len(phonetic_matches),
    )
    return "", "", "ambiguous"


def definition_candidates(
    group: OxfordGroup,
    definition_index: Mapping[tuple[str, str], list[DatasetDefinition]],
) -> list[DatasetDefinition]:
    allowed_pos = DATASET_POS_BY_OXFORD_CATEGORY.get(
        group.lexical_category, {group.lexical_category}
    )

    def candidates_for(words: Iterable[str]) -> list[DatasetDefinition]:
        matches: list[DatasetDefinition] = []
        seen: set[int] = set()
        for word in words:
            for part_of_speech in allowed_pos:
                for candidate in definition_index.get((word, part_of_speech), []):
                    if candidate.ordinal not in seen:
                        seen.add(candidate.ordinal)
                        matches.append(candidate)
        return matches

    base_matches = candidates_for(group.base_words)
    if base_matches:
        return base_matches
    return candidates_for([*group.us_variants, *group.gb_variants])


def group_spellings(group: OxfordGroup) -> tuple[str, str]:
    base_word = group.base_words[0] if group.base_words else ""
    word_us = group.us_variants[0] if group.us_variants else base_word
    word_gb = group.gb_variants[0] if group.gb_variants else base_word
    if len(group.us_variants) > 1:
        LOGGER.warning(
            "%s has multiple US spellings; using %r and ignoring %r",
            group.source_lexical_key,
            group.us_variants[0],
            group.us_variants[1:],
        )
    if len(group.gb_variants) > 1:
        LOGGER.warning(
            "%s has multiple GB spellings; using %r and ignoring %r",
            group.source_lexical_key,
            group.gb_variants[0],
            group.gb_variants[1:],
        )
    return word_us, word_gb


def iter_senses(senses: Iterable[Mapping[str, Any]]) -> Iterator[Mapping[str, Any]]:
    for sense in senses:
        yield sense
        yield from iter_senses(sense.get("subsenses") or [])


def normalize_word(value: Any) -> str:
    text = unicodedata.normalize("NFC", str(value or "").strip())
    return " ".join(text.lower().split())


def normalize_category(value: Any) -> str:
    return normalize_word(value).replace("_", " ")


def normalize_marker(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("id") or value.get("text") or ""
    text = normalize_word(value).replace("_", " ").replace("-", " ")
    return " ".join(text.split())


def normalize_ipa(value: Any) -> str:
    text = unicodedata.normalize("NFC", str(value or "").strip())
    if not text:
        return ""
    text = text.strip("/[]").strip()
    return f"/{text}/" if text else ""


def comparable_ipa(value: Any) -> str:
    return normalize_ipa(value).strip("/").replace(" ", "")


def append_unique(values: list[Any], value: Any) -> None:
    if value not in values:
        values.append(value)


def regions_from_items(items: Iterable[Any]) -> set[Dialect]:
    regions: set[Dialect] = set()
    for item in items:
        marker = normalize_marker(item)
        if marker in US_REGION_MARKERS:
            regions.add(Dialect.US)
        if marker in GB_REGION_MARKERS:
            regions.add(Dialect.GB)
    return regions


def source_key(result_id: str, lexical_category: str) -> str:
    encoded_id = quote(normalize_word(result_id), safe="._-")
    encoded_category = quote(normalize_category(lexical_category), safe="._-")
    return f"oxford:{encoded_id}:{encoded_category}"
