#!/usr/bin/env python3
"""Import Oxford API cache into ``oxford_lexical_entries`` (offline tooling).

The bot runtime does not read this table; use it only when rebuilding or analyzing
Oxford cache dumps. Day-to-day card content comes from ``oald_entries`` via
``uv run oald-import``.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from scripts.oald.cli_utils import (
    LOG_LEVELS,
    configure_logging,
    positive_integer,
    resolve_db_url,
)
from scripts.oald.oxford_import import (
    OxfordCacheError,
    OxfordDatabaseError,
    build_rows,
    import_rows,
    load_definition_index,
    parse_cache_files,
)
from scripts.oald.oxford_import.parse import log_summary

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE_DIR = ROOT / "source" / "oxford_api" / "translations_en_ru"
DEFAULT_WORDS_JSON = ROOT / "data" / "enriched" / "words.json"

LOGGER = logging.getLogger("tgbot.oxford_import")

__all__ = [
    "OxfordCacheError",
    "OxfordDatabaseError",
    "build_rows",
    "import_rows",
    "load_definition_index",
    "main",
    "parse_args",
    "parse_cache_files",
]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)

    if not args.source_dir.is_dir():
        LOGGER.error("Oxford cache directory does not exist: %s", args.source_dir)
        return 2
    if not args.words_json.is_file():
        LOGGER.error("Definition JSON does not exist: %s", args.words_json)
        return 2
    if not args.dry_run and not args.db_url:
        LOGGER.error(
            "PostgreSQL URL is required: use --database-url or set OALD_DATABASE_URL"
        )
        return 2

    try:
        LOGGER.info("Reading Oxford cache from %s", args.source_dir)
        groups, file_stats = parse_cache_files(
            args.source_dir,
            limit_files=args.limit_files,
            strict=args.strict,
        )
        definition_index = load_definition_index(args.words_json)
        rows, row_stats = build_rows(groups, definition_index)
        log_summary(file_stats, row_stats)
        if args.dry_run:
            LOGGER.info("Dry-run complete; no database changes made")
            return 0

        imported = import_rows(rows, args.db_url, batch_size=args.batch_size)
        LOGGER.info("Oxford import complete: %s rows processed", f"{imported:,}")
        return 0
    except (OxfordCacheError, OxfordDatabaseError) as exc:
        LOGGER.error("Oxford import failed: %s", exc)
        return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dir",
        type=Path,
        default=DEFAULT_SOURCE_DIR,
        help=f"Oxford cache directory (default: {DEFAULT_SOURCE_DIR})",
    )
    parser.add_argument(
        "--words-json",
        type=Path,
        default=DEFAULT_WORDS_JSON,
        help=f"Definition source JSON (default: {DEFAULT_WORDS_JSON})",
    )
    parser.add_argument(
        "--database-url",
        dest="db_url",
        default=resolve_db_url(),
        help="PostgreSQL URL; defaults to OALD_DATABASE_URL",
    )
    parser.add_argument(
        "--batch-size",
        type=positive_integer,
        default=500,
        help="Rows per PostgreSQL batch (default: 500)",
    )
    parser.add_argument(
        "--limit-files",
        type=positive_integer,
        help="Process only the first N cache files",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and report without connecting to PostgreSQL",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Stop on the first malformed cache file",
    )
    parser.add_argument(
        "--log-level",
        choices=LOG_LEVELS,
        default="INFO",
        help="Terminal log verbosity (default: INFO)",
    )
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
