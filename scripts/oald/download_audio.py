#!/usr/bin/env python3
"""Download OALD pronunciation audio and store Telegram voice variants."""

from __future__ import annotations

import argparse
import logging

from scripts.oald.audio import (
    AudioConversionError,
    AudioDownloadError,
    AudioRateLimitError,
    DownloadedAudio,
    OaldAudioDatabaseError,
    VoiceAudio,
    download_audio_file,
    download_audio_to_postgres,
    download_with_retries,
    transcode_audio_to_voice,
    validate_voice_payload,
)
from scripts.oald.audio.constants import DEFAULT_MAX_AUDIO_BYTES
from scripts.oald.cli_utils import (
    LOG_LEVELS,
    configure_logging,
    nonnegative_float,
    nonnegative_integer,
    positive_float,
    positive_integer,
    resolve_db_url,
)
from tgbot.db.models import Dialect

LOGGER = logging.getLogger("tgbot.oald_audio_download")

__all__ = [
    "AudioConversionError",
    "AudioDownloadError",
    "AudioRateLimitError",
    "DownloadedAudio",
    "OaldAudioDatabaseError",
    "VoiceAudio",
    "download_audio_file",
    "download_audio_to_postgres",
    "download_with_retries",
    "main",
    "parse_args",
    "transcode_audio_to_voice",
    "validate_voice_payload",
]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)
    if not args.db_url:
        LOGGER.error(
            "PostgreSQL URL is required: use --database-url or set OALD_DATABASE_URL"
        )
        return 2

    try:
        stats = download_audio_to_postgres(
            args.db_url,
            dialects=args.dialects,
            limit=args.limit,
            force=args.force,
            request_delay=args.request_delay,
            timeout=args.timeout,
            retries=args.retries,
            retry_backoff=args.retry_backoff,
            max_audio_bytes=args.max_audio_bytes,
            fail_fast=args.fail_fast,
        )
        LOGGER.info(
            "Audio run complete: candidates=%s downloaded=%s reused=%s "
            "download_failed=%s voices_prepared=%s conversion_failed=%s "
            "stored_bytes=%s voice_bytes=%s rate_limited=%s",
            f"{stats.candidates:,}",
            f"{stats.downloaded:,}",
            f"{stats.reused_originals:,}",
            f"{stats.failed:,}",
            f"{stats.voices_prepared:,}",
            f"{stats.conversion_failed:,}",
            f"{stats.stored_bytes:,}",
            f"{stats.voice_bytes:,}",
            stats.rate_limited,
        )
        return 3 if stats.rate_limited else 0
    except (AudioDownloadError, AudioConversionError, OaldAudioDatabaseError) as exc:
        LOGGER.error("OALD audio run failed: %s", exc)
        return 1


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        dest="db_url",
        default=resolve_db_url(),
        help="OALD PostgreSQL URL; defaults to OALD_DATABASE_URL",
    )
    parser.add_argument(
        "--dialects",
        nargs="+",
        choices=tuple(Dialect),
        default=[Dialect.US, Dialect.GB],
        help="Audio dialects to download (default: us gb)",
    )
    parser.add_argument(
        "--limit",
        type=positive_integer,
        help="Process at most N unique audio URLs",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Download originals again and rebuild Telegram voice variants",
    )
    parser.add_argument(
        "--request-delay",
        type=nonnegative_float,
        default=0.5,
        help="Delay between different URLs in seconds (default: 0.5)",
    )
    parser.add_argument(
        "--timeout",
        type=positive_float,
        default=30.0,
        help="Per-request timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--retries",
        type=nonnegative_integer,
        default=3,
        help="Retries for temporary errors (default: 3)",
    )
    parser.add_argument(
        "--retry-backoff",
        type=nonnegative_float,
        default=2.0,
        help="Initial exponential retry delay in seconds (default: 2)",
    )
    parser.add_argument(
        "--max-audio-bytes",
        type=positive_integer,
        default=DEFAULT_MAX_AUDIO_BYTES,
        help="Maximum accepted file size (default: 10485760)",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on the first non-rate-limit download failure",
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
