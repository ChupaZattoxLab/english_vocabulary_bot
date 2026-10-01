#!/usr/bin/env python3
"""Import OALD card entries from words.json into PostgreSQL (bot content source)."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from scripts.oald.cli_utils import (
    LOG_LEVELS,
    configure_logging,
    positive_integer,
    resolve_admin_db_url,
    resolve_db_url,
)
from scripts.oald.oald_import import (
    ImportResult,
    OaldDatabaseError,
    OaldEntry,
    OaldValidationError,
    import_entries,
    load_entries,
)
from scripts.oald.oald_import.parse import log_input_summary
from tgbot.db.sync import ensure_database_exists

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_JSON_PATH = ROOT / "data" / "oald" / "words.json"

LOGGER = logging.getLogger("tgbot.oald_import")

__all__ = [
    "ImportResult",
    "OaldDatabaseError",
    "OaldEntry",
    "OaldValidationError",
    "import_entries",
    "load_entries",
    "main",
    "parse_args",
]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)

    if not args.json.is_file():
        LOGGER.error("OALD JSON file does not exist: %s", args.json)
        return 2
    if not args.dry_run and not args.db_url:
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

        try:
            created = ensure_database_exists(
                args.db_url,
                admin_db_url=args.admin_db_url,
            )
        except ValueError as exc:
            raise OaldDatabaseError(str(exc)) from exc
        except Exception as exc:
            raise OaldDatabaseError(
                "could not create the target database; provide "
                "--admin-database-url for a role allowed to create "
                "databases"
            ) from exc
        if created:
            LOGGER.info("Created target OALD PostgreSQL database")
        result = import_entries(
            entries,
            args.db_url,
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
        dest="db_url",
        default=resolve_db_url(),
        help="Target PostgreSQL URL; defaults to OALD_DATABASE_URL",
    )
    parser.add_argument(
        "--admin-database-url",
        dest="admin_db_url",
        default=resolve_admin_db_url(),
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


if __name__ == "__main__":
    raise SystemExit(main())
