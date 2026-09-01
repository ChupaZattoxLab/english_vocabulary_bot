"""Parse and validate OALD words.json entries."""

from __future__ import annotations

import json
import logging
import unicodedata
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from scripts.oald.oald_import.models import OaldEntry, OaldValidationError
from tgbot.db.models import CefrLevel

EXPECTED_FIELDS = {
    "word_us",
    "word_gb",
    "lexical_category",
    "cefr",
    "definition_url_oxford",
    "definition_url_cambridge",
    "ipa_us",
    "ipa_gb",
    "definition",
    "example",
    "audio_source_us",
    "audio_source_gb",
    "translations",
}

LOGGER = logging.getLogger("tgbot.oald_import")


def load_entries(
    json_path: Path,
    strict: bool = False,
) -> tuple[list[OaldEntry], Counter[str]]:
    try:
        raw_rows = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise OaldValidationError(f"could not read {json_path}: {exc}") from exc
    if not isinstance(raw_rows, list):
        raise OaldValidationError("the OALD JSON root must be an array")

    entries: list[OaldEntry] = []
    stats: Counter[str] = Counter()
    seen_definition_urls: set[str] = set()
    for row_number, raw in enumerate(raw_rows, start=1):
        stats["rows_read"] += 1
        try:
            entry = parse_entry(raw, row_number)
            if entry.definition_url_oxford in seen_definition_urls:
                raise OaldValidationError(
                    f"row {row_number}: duplicate definition_url_oxford "
                    f"{entry.definition_url_oxford!r}"
                )
        except OaldValidationError as exc:
            stats["invalid_rows"] += 1
            if strict:
                raise
            LOGGER.error("Skipping invalid OALD entry: %s", exc)
            continue
        seen_definition_urls.add(entry.definition_url_oxford)
        entries.append(entry)
        stats["valid_rows"] += 1
        stats["audio_references_us"] += len(entry.audio_source_us)
        stats["audio_references_gb"] += len(entry.audio_source_gb)

    unique_urls = {
        source_url for entry in entries for _, _, source_url in entry.audio_references()
    }
    stats["unique_audio_urls"] = len(unique_urls)
    return entries, stats


def parse_entry(raw: Any, row_number: int) -> OaldEntry:
    if not isinstance(raw, Mapping):
        raise OaldValidationError(f"row {row_number}: entry must be an object")
    missing_fields = sorted(EXPECTED_FIELDS - set(raw))
    if missing_fields:
        raise OaldValidationError(
            f"row {row_number}: missing fields: {', '.join(missing_fields)}"
        )

    cefr_text = required_text(raw, "cefr", row_number).lower()
    try:
        cefr = CefrLevel(cefr_text)
    except ValueError as exc:
        raise OaldValidationError(
            f"row {row_number}: unsupported CEFR value {cefr_text!r}"
        ) from exc

    definition_url = required_text(raw, "definition_url_oxford", row_number)
    if urlparse(definition_url).scheme not in {"http", "https"}:
        raise OaldValidationError(
            f"row {row_number}: definition_url_oxford must be an HTTP(S) URL"
        )
    cambridge_url = optional_text(raw, "definition_url_cambridge", row_number)
    if cambridge_url and urlparse(cambridge_url).scheme not in {"http", "https"}:
        raise OaldValidationError(
            f"row {row_number}: definition_url_cambridge must be an HTTP(S) URL"
        )

    return OaldEntry(
        word_us=required_text(raw, "word_us", row_number),
        word_gb=required_text(raw, "word_gb", row_number),
        lexical_category=required_text(raw, "lexical_category", row_number),
        cefr=cefr,
        definition_url_oxford=definition_url,
        definition_url_cambridge=cambridge_url,
        ipa_us=string_list(raw, "ipa_us", row_number),
        ipa_gb=string_list(raw, "ipa_gb", row_number),
        definition=required_text(raw, "definition", row_number),
        example=required_text(raw, "example", row_number),
        audio_source_us=string_list(
            raw,
            "audio_source_us",
            row_number,
            require_urls=True,
        ),
        audio_source_gb=string_list(
            raw,
            "audio_source_gb",
            row_number,
            require_urls=True,
        ),
        translations=validate_translations(raw.get("translations"), row_number),
    )


def required_text(raw: Mapping[str, Any], field: str, row_number: int) -> str:
    value = raw.get(field)
    if not isinstance(value, str) or not normalize_text(value):
        raise OaldValidationError(
            f"row {row_number}: {field} must be a non-empty string"
        )
    return normalize_text(value)


def optional_text(raw: Mapping[str, Any], field: str, row_number: int) -> str:
    value = raw.get(field)
    if not isinstance(value, str):
        raise OaldValidationError(f"row {row_number}: {field} must be a string")
    return normalize_text(value)


def string_list(
    raw: Mapping[str, Any],
    field: str,
    row_number: int,
    require_urls: bool = False,
) -> list[str]:
    value = raw.get(field)
    if not isinstance(value, list):
        raise OaldValidationError(f"row {row_number}: {field} must be a JSON array")
    result: list[str] = []
    for position, item in enumerate(value):
        if not isinstance(item, str):
            raise OaldValidationError(
                f"row {row_number}: {field}[{position}] must be a string"
            )
        normalized = normalize_text(item)
        if not normalized:
            raise OaldValidationError(
                f"row {row_number}: {field}[{position}] must not be empty"
            )
        if require_urls and urlparse(normalized).scheme not in {"http", "https"}:
            raise OaldValidationError(
                f"row {row_number}: {field}[{position}] must be an HTTP(S) URL"
            )
        result.append(normalized)
    return result


def validate_translations(value: Any, row_number: int) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise OaldValidationError(f"row {row_number}: translations must be an object")
    ru = value.get("ru")
    if not isinstance(ru, dict):
        raise OaldValidationError(
            f"row {row_number}: translations.ru must be an object"
        )
    main = ru.get("main")
    also = ru.get("also")
    if not isinstance(main, str):
        raise OaldValidationError(
            f"row {row_number}: translations.ru.main must be a string"
        )
    if not isinstance(also, list) or not all(isinstance(item, str) for item in also):
        raise OaldValidationError(
            f"row {row_number}: translations.ru.also must be an array of strings"
        )
    return value


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def log_input_summary(stats: Counter[str]) -> None:
    LOGGER.info(
        "OALD JSON: read=%s valid=%s invalid=%s audio_refs(us=%s gb=%s total=%s) "
        "unique_audio_urls=%s",
        f"{stats['rows_read']:,}",
        f"{stats['valid_rows']:,}",
        f"{stats['invalid_rows']:,}",
        f"{stats['audio_references_us']:,}",
        f"{stats['audio_references_gb']:,}",
        f"{stats['audio_references_us'] + stats['audio_references_gb']:,}",
        f"{stats['unique_audio_urls']:,}",
    )
