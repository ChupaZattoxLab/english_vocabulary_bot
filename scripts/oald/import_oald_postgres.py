#!/usr/bin/env python3
"""Incrementally import OALD words.json into an already-migrated PostgreSQL database."""

from __future__ import annotations

import argparse
import json
import logging
import os
import unicodedata
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from .oald_preflight import require_oald_schema
except ImportError:  # running as a plain script
    from oald_preflight import require_oald_schema  # type: ignore[no-redef]


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JSON_PATH = ROOT / "data" / "oald" / "words.json"
LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
VALID_CEFR_LEVELS = {"a1", "a2", "b1", "b2", "c1", "c2"}
DEFAULT_CONNECT_TIMEOUT = 10
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

UPSERT_ENTRY_SQL = """
INSERT INTO oald_entries (
    word_us,
    word_gb,
    lexical_category,
    cefr,
    definition_url_oxford,
    definition_url_cambridge,
    ipa_us,
    ipa_gb,
    definition,
    example,
    audio_source_us,
    audio_source_gb,
    translations
) VALUES (
    %(word_us)s,
    %(word_gb)s,
    %(lexical_category)s,
    %(cefr)s,
    %(definition_url_oxford)s,
    %(definition_url_cambridge)s,
    %(ipa_us)s,
    %(ipa_gb)s,
    %(definition)s,
    %(example)s,
    %(audio_source_us)s,
    %(audio_source_gb)s,
    %(translations)s
)
ON CONFLICT (definition_url_oxford) DO UPDATE SET
    word_us = EXCLUDED.word_us,
    word_gb = EXCLUDED.word_gb,
    lexical_category = EXCLUDED.lexical_category,
    cefr = EXCLUDED.cefr,
    definition_url_cambridge = EXCLUDED.definition_url_cambridge,
    ipa_us = EXCLUDED.ipa_us,
    ipa_gb = EXCLUDED.ipa_gb,
    definition = EXCLUDED.definition,
    example = EXCLUDED.example,
    audio_source_us = EXCLUDED.audio_source_us,
    audio_source_gb = EXCLUDED.audio_source_gb,
    translations = EXCLUDED.translations,
    updated_at = CURRENT_TIMESTAMP
RETURNING id
"""

INSERT_AUDIO_FILE_SQL = """
INSERT INTO oald_audio_files (source_url)
VALUES (%s)
ON CONFLICT (source_url) DO NOTHING
"""

INSERT_AUDIO_LINK_SQL = """
INSERT INTO oald_entry_audio_sources (
    entry_id,
    dialect,
    source_position,
    source_url
) VALUES (%s, %s, %s, %s)
"""


class OaldValidationError(ValueError):
    """Raised when OALD JSON does not match the expected schema."""


class OaldDatabaseError(RuntimeError):
    """Raised when the OALD PostgreSQL setup or import fails."""


@dataclass(frozen=True)
class OaldEntry:
    word_us: str
    word_gb: str
    lexical_category: str
    cefr: str
    definition_url_oxford: str
    definition_url_cambridge: str
    ipa_us: list[str]
    ipa_gb: list[str]
    definition: str
    example: str
    audio_source_us: list[str]
    audio_source_gb: list[str]
    translations: dict[str, Any]

    def parameters(self, jsonb_factory: Any) -> dict[str, Any]:
        return {
            "word_us": self.word_us,
            "word_gb": self.word_gb,
            "lexical_category": self.lexical_category,
            "cefr": self.cefr,
            "definition_url_oxford": self.definition_url_oxford,
            "definition_url_cambridge": self.definition_url_cambridge,
            "ipa_us": self.ipa_us,
            "ipa_gb": self.ipa_gb,
            "definition": self.definition,
            "example": self.example,
            "audio_source_us": self.audio_source_us,
            "audio_source_gb": self.audio_source_gb,
            "translations": jsonb_factory(self.translations),
        }

    def audio_references(self) -> Iterator[tuple[str, int, str]]:
        for dialect, urls in (
            ("us", self.audio_source_us),
            ("gb", self.audio_source_gb),
        ):
            for position, source_url in enumerate(urls):
                yield dialect, position, source_url


@dataclass(frozen=True)
class ImportResult:
    entries: int
    audio_references: int
    unique_audio_urls: int


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())


def connection_options(database_url: str) -> dict[str, Any]:
    if urlparse(database_url).hostname == "localhost":
        return {"hostaddr": "127.0.0.1"}
    return {}


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
    *,
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


def parse_entry(raw: Any, row_number: int) -> OaldEntry:
    if not isinstance(raw, Mapping):
        raise OaldValidationError(f"row {row_number}: entry must be an object")
    missing_fields = sorted(EXPECTED_FIELDS - set(raw))
    if missing_fields:
        raise OaldValidationError(
            f"row {row_number}: missing fields: {', '.join(missing_fields)}"
        )

    cefr = required_text(raw, "cefr", row_number).lower()
    if cefr not in VALID_CEFR_LEVELS:
        raise OaldValidationError(f"row {row_number}: unsupported CEFR value {cefr!r}")

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


def load_entries(
    json_path: Path,
    *,
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


def iter_batches(
    entries: Iterable[OaldEntry],
    batch_size: int,
) -> Iterator[list[OaldEntry]]:
    batch: list[OaldEntry] = []
    for entry in entries:
        batch.append(entry)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch


def _load_psycopg() -> Any:
    try:
        import psycopg
    except ImportError as exc:
        raise OaldDatabaseError("psycopg is not installed; run: uv sync") from exc
    return psycopg


def ensure_database_exists(
    database_url: str,
    *,
    admin_database_url: str | None = None,
) -> bool:
    """Ensure the target database exists; return True when it was created."""
    psycopg = _load_psycopg()
    try:
        from psycopg import sql
        from psycopg.conninfo import conninfo_to_dict, make_conninfo

        target_parameters = conninfo_to_dict(database_url)
        target_database = target_parameters.get("dbname")
        if not isinstance(target_database, str) or not target_database:
            raise OaldDatabaseError(
                "the target database URL must include a database name"
            )
        if admin_database_url:
            admin_connection_info = admin_database_url
        else:
            admin_parameters = {
                key: value
                for key, value in target_parameters.items()
                if isinstance(value, str)
            }
            admin_parameters["dbname"] = "postgres"
            if admin_parameters.get("host") == "localhost" and not admin_parameters.get(
                "hostaddr"
            ):
                admin_parameters["hostaddr"] = "127.0.0.1"
            admin_connection_info = make_conninfo(**admin_parameters)

        with psycopg.connect(
            admin_connection_info,
            autocommit=True,
            connect_timeout=DEFAULT_CONNECT_TIMEOUT,
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT 1 FROM pg_database WHERE datname = %s",
                    (target_database,),
                )
                if cursor.fetchone():
                    return False
                try:
                    cursor.execute(
                        sql.SQL("CREATE DATABASE {}").format(
                            sql.Identifier(target_database)
                        )
                    )
                except psycopg.Error as exc:
                    raise OaldDatabaseError(
                        "could not create the target database; provide "
                        "--admin-database-url for a role allowed to create "
                        "databases"
                    ) from exc
        return True
    except OaldDatabaseError:
        raise
    except psycopg.Error:
        try:
            with psycopg.connect(
                database_url,
                connect_timeout=DEFAULT_CONNECT_TIMEOUT,
                **connection_options(database_url),
            ):
                return False
        except psycopg.Error as target_exc:
            raise OaldDatabaseError(
                "could not connect to the target or administrative PostgreSQL database"
            ) from target_exc


def import_entries(
    entries: Iterable[OaldEntry],
    database_url: str,
    *,
    batch_size: int = 500,
) -> ImportResult:
    psycopg = _load_psycopg()
    try:
        from psycopg.types.json import Jsonb

        entry_count = 0
        audio_reference_count = 0
        unique_audio_urls: set[str] = set()
        with psycopg.connect(
            database_url,
            connect_timeout=DEFAULT_CONNECT_TIMEOUT,
            **connection_options(database_url),
        ) as connection:
            with connection.cursor() as cursor:
                require_oald_schema(cursor)
                LOGGER.info("Alembic-managed OALD schema is ready")
                for batch in iter_batches(entries, batch_size):
                    imported_ids: list[int] = []
                    links: list[tuple[int, str, int, str]] = []
                    batch_urls: set[str] = set()

                    for entry in batch:
                        cursor.execute(
                            UPSERT_ENTRY_SQL,
                            entry.parameters(Jsonb),
                        )
                        result = cursor.fetchone()
                        if result is None:
                            raise OaldDatabaseError(
                                "entry upsert did not return a database ID"
                            )
                        entry_id = int(result[0])
                        imported_ids.append(entry_id)
                        for dialect, position, source_url in entry.audio_references():
                            links.append((entry_id, dialect, position, source_url))
                            batch_urls.add(source_url)

                    if imported_ids:
                        cursor.execute(
                            """
                            DELETE FROM oald_entry_audio_sources
                            WHERE entry_id = ANY(%s)
                            """,
                            (imported_ids,),
                        )
                    if batch_urls:
                        cursor.executemany(
                            INSERT_AUDIO_FILE_SQL,
                            [(source_url,) for source_url in sorted(batch_urls)],
                        )
                    if links:
                        cursor.executemany(INSERT_AUDIO_LINK_SQL, links)

                    entry_count += len(batch)
                    audio_reference_count += len(links)
                    unique_audio_urls.update(batch_urls)
                    LOGGER.info(
                        "Imported batch=%s; entries=%s; audio references=%s",
                        f"{len(batch):,}",
                        f"{entry_count:,}",
                        f"{audio_reference_count:,}",
                    )

        return ImportResult(
            entries=entry_count,
            audio_references=audio_reference_count,
            unique_audio_urls=len(unique_audio_urls),
        )
    except OaldDatabaseError:
        raise
    except psycopg.Error as exc:
        raise OaldDatabaseError(
            "PostgreSQL OALD import failed; the transaction was rolled back"
        ) from exc


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


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        type=Path,
        default=DEFAULT_JSON_PATH,
        help=f"OALD words JSON (default: {DEFAULT_JSON_PATH})",
    )
    parser.add_argument(
        "--database-url",
        default=os.environ.get("OALD_DATABASE_URL"),
        help="Target PostgreSQL URL; defaults to OALD_DATABASE_URL",
    )
    parser.add_argument(
        "--admin-database-url",
        default=os.environ.get("OALD_ADMIN_DATABASE_URL"),
        help=(
            "Optional PostgreSQL admin URL used only to create a missing "
            "target database; defaults to the target server's postgres database"
        ),
    )
    parser.add_argument(
        "--batch-size",
        type=positive_integer,
        default=500,
        help="Entries per PostgreSQL batch (default: 500)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report without creating a database or changing data",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Stop on the first invalid JSON entry instead of skipping it",
    )
    parser.add_argument(
        "--log-level",
        choices=LOG_LEVELS,
        default="INFO",
        help="Terminal log verbosity (default: INFO)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)

    if not args.json.is_file():
        LOGGER.error("OALD JSON file does not exist: %s", args.json)
        return 2
    if not args.dry_run and not args.database_url:
        LOGGER.error(
            "PostgreSQL URL is required: use --database-url or set OALD_DATABASE_URL"
        )
        return 2

    try:
        LOGGER.info("Reading OALD entries from %s", args.json)
        entries, stats = load_entries(args.json, strict=args.strict)
        log_input_summary(stats)
        if args.dry_run:
            LOGGER.info("Dry-run complete; no database changes made")
            return 0

        created = ensure_database_exists(
            args.database_url,
            admin_database_url=args.admin_database_url,
        )
        if created:
            LOGGER.info("Created target OALD PostgreSQL database")
        result = import_entries(
            entries,
            args.database_url,
            batch_size=args.batch_size,
        )
        LOGGER.info(
            "OALD import complete: entries=%s audio_references=%s unique_audio_urls=%s",
            f"{result.entries:,}",
            f"{result.audio_references:,}",
            f"{result.unique_audio_urls:,}",
        )
        return 0
    except (OaldValidationError, OaldDatabaseError) as exc:
        LOGGER.error("OALD import failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
