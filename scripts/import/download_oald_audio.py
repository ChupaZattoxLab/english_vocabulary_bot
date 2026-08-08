#!/usr/bin/env python3
"""Download OALD audio and prepare Telegram OGG Opus voice messages."""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

try:
    from .oald_preflight import require_oald_schema
except ImportError:
    from oald_preflight import require_oald_schema  # type: ignore[no-redef]


LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")
LOGGER = logging.getLogger("vocabulary.oald_audio_download")
DEFAULT_MAX_AUDIO_BYTES = 10 * 1024 * 1024
DEFAULT_CONNECT_TIMEOUT = 10
RETRYABLE_HTTP_STATUS = {408, 425, 500, 502, 503, 504}
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/128.0.0.0 Safari/537.36"
)
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "audio/ogg,audio/mpeg,audio/*;q=0.9,*/*;q=0.1",
    "Referer": "https://www.oxfordlearnersdictionaries.com/",
}

CANDIDATE_SQL = """
SELECT
    files.source_url,
    min(entries.word_us) AS example_word,
    array_agg(DISTINCT links.dialect ORDER BY links.dialect) AS dialects,
    files.audio_data IS NOT NULL AS has_original
FROM oald_audio_files AS files
JOIN oald_entry_audio_sources AS links
  ON links.source_url = files.source_url
JOIN oald_entries AS entries
  ON entries.id = links.entry_id
LEFT JOIN oald_audio_variants AS variants
  ON variants.source_url = files.source_url
 AND variants.variant_type = 'telegram_voice_opus'
WHERE links.dialect = ANY(%s)
  AND (
      %s
      OR files.audio_data IS NULL
      OR variants.audio_data IS NULL
      OR variants.source_sha256 <> files.sha256
  )
  AND (%s::text[] IS NULL OR files.source_url = ANY(%s::text[]))
GROUP BY files.source_url, files.audio_data IS NOT NULL
ORDER BY files.source_url
LIMIT %s
"""

LOAD_STORED_AUDIO_SQL = """
SELECT audio_data, content_type, filename, sha256, last_http_status
FROM oald_audio_files
WHERE source_url = %s AND audio_data IS NOT NULL
"""

STORE_SUCCESS_SQL = """
UPDATE oald_audio_files
SET audio_data = %s,
    content_type = %s,
    filename = %s,
    size_bytes = %s,
    sha256 = %s,
    download_status = 'downloaded',
    last_http_status = %s,
    last_error = '',
    attempt_count = attempt_count + %s,
    last_attempted_at = CURRENT_TIMESTAMP,
    downloaded_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP
WHERE source_url = %s
"""

STORE_FAILURE_SQL = """
UPDATE oald_audio_files
SET download_status = CASE
        WHEN audio_data IS NULL THEN %s
        ELSE 'downloaded'
    END,
    last_http_status = %s,
    last_error = %s,
    attempt_count = attempt_count + %s,
    last_attempted_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP
WHERE source_url = %s
"""

STORE_VOICE_SUCCESS_SQL = """
INSERT INTO oald_audio_variants (
    source_url, variant_type, source_sha256, audio_data, content_type,
    filename, size_bytes, sha256, conversion_status, last_error,
    attempt_count, converted_at
) VALUES (
    %s, 'telegram_voice_opus', %s, %s, 'audio/ogg',
    %s, %s, %s, 'prepared', '', 1, CURRENT_TIMESTAMP
)
ON CONFLICT (source_url, variant_type) DO UPDATE SET
    source_sha256 = EXCLUDED.source_sha256,
    audio_data = EXCLUDED.audio_data,
    content_type = EXCLUDED.content_type,
    filename = EXCLUDED.filename,
    size_bytes = EXCLUDED.size_bytes,
    sha256 = EXCLUDED.sha256,
    conversion_status = 'prepared',
    last_error = '',
    attempt_count = oald_audio_variants.attempt_count + 1,
    converted_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP
"""

STORE_VOICE_FAILURE_SQL = """
INSERT INTO oald_audio_variants (
    source_url, variant_type, source_sha256, conversion_status,
    last_error, attempt_count
) VALUES (%s, 'telegram_voice_opus', %s, 'failed', %s, 1)
ON CONFLICT (source_url, variant_type) DO UPDATE SET
    source_sha256 = CASE
        WHEN oald_audio_variants.source_sha256 = EXCLUDED.source_sha256
            THEN oald_audio_variants.source_sha256
        ELSE EXCLUDED.source_sha256
    END,
    audio_data = CASE
        WHEN oald_audio_variants.source_sha256 = EXCLUDED.source_sha256
            THEN oald_audio_variants.audio_data
        ELSE NULL
    END,
    content_type = CASE
        WHEN oald_audio_variants.source_sha256 = EXCLUDED.source_sha256
            THEN oald_audio_variants.content_type
        ELSE ''
    END,
    filename = CASE
        WHEN oald_audio_variants.source_sha256 = EXCLUDED.source_sha256
            THEN oald_audio_variants.filename
        ELSE ''
    END,
    size_bytes = CASE
        WHEN oald_audio_variants.source_sha256 = EXCLUDED.source_sha256
            THEN oald_audio_variants.size_bytes
        ELSE NULL
    END,
    sha256 = CASE
        WHEN oald_audio_variants.source_sha256 = EXCLUDED.source_sha256
            THEN oald_audio_variants.sha256
        ELSE ''
    END,
    conversion_status = CASE
        WHEN oald_audio_variants.source_sha256 = EXCLUDED.source_sha256
         AND oald_audio_variants.audio_data IS NOT NULL THEN 'prepared'
        ELSE 'failed'
    END,
    last_error = EXCLUDED.last_error,
    attempt_count = oald_audio_variants.attempt_count + 1,
    converted_at = CASE
        WHEN oald_audio_variants.source_sha256 = EXCLUDED.source_sha256
            THEN oald_audio_variants.converted_at
        ELSE NULL
    END,
    updated_at = CURRENT_TIMESTAMP
"""


class OaldAudioError(RuntimeError):
    """Base error for OALD audio processing."""


class OaldAudioDatabaseError(OaldAudioError):
    """Raised when PostgreSQL audio access fails."""


class AudioDownloadError(OaldAudioError):
    """Raised when one audio file cannot be downloaded or validated."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        status_code: int | None = None,
        attempts: int = 1,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.status_code = status_code
        self.attempts = attempts


class AudioRateLimitError(AudioDownloadError):
    """Raised for HTTP 429 so the complete run can stop immediately."""


class AudioConversionError(OaldAudioError):
    """Raised when an original pronunciation cannot become Telegram voice."""


@dataclass(frozen=True)
class AudioCandidate:
    source_url: str
    example_word: str
    dialects: tuple[str, ...]
    has_original: bool


@dataclass(frozen=True)
class DownloadedAudio:
    data: bytes
    content_type: str
    filename: str
    sha256: str
    http_status: int | None = None


@dataclass(frozen=True)
class VoiceAudio:
    data: bytes
    content_type: str
    filename: str
    sha256: str


@dataclass
class DownloadStats:
    candidates: int = 0
    downloaded: int = 0
    reused_originals: int = 0
    failed: int = 0
    voices_prepared: int = 0
    conversion_failed: int = 0
    rate_limited: bool = False
    stored_bytes: int = 0
    voice_bytes: int = 0


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def connection_options(database_url: str) -> dict[str, str]:
    if urlparse(database_url).hostname == "localhost":
        return {"hostaddr": "127.0.0.1"}
    return {}


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def nonnegative_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def nonnegative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def filename_from_response(response: Any, fallback_url: str) -> str:
    headers = response.headers
    disposition = str(headers.get("Content-Disposition", "") or "")
    encoded_match = re.search(
        r"filename\*=UTF-8''([^;]+)",
        disposition,
        flags=re.IGNORECASE,
    )
    if encoded_match:
        return Path(unquote(encoded_match.group(1).strip())).name
    plain_match = re.search(
        r'filename="?([^";]+)"?',
        disposition,
        flags=re.IGNORECASE,
    )
    if plain_match:
        return Path(plain_match.group(1).strip()).name

    final_url = response.geturl() if hasattr(response, "geturl") else fallback_url
    filename = Path(unquote(urlparse(final_url).path)).name
    return filename or "pronunciation-audio"


def declared_content_type(headers: Any) -> str:
    if hasattr(headers, "get_content_type"):
        content_type = str(headers.get_content_type() or "")
    else:
        content_type = str(headers.get("Content-Type", "") or "").split(";", 1)[0]
    return content_type.strip().lower()


def detected_audio_content_type(data: bytes) -> str:
    if data.startswith(b"OggS"):
        return "audio/ogg"
    if data.startswith(b"ID3") or (
        len(data) >= 2 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0
    ):
        return "audio/mpeg"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "audio/wav"
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return "audio/mp4"
    return ""


def validate_audio_payload(data: bytes, declared_type: str) -> str:
    if not data:
        raise AudioDownloadError("the server returned an empty response")
    prefix = data[:256].lstrip().lower()
    if prefix.startswith(b"<!doctype html") or prefix.startswith(b"<html"):
        raise AudioDownloadError("the server returned HTML instead of audio")
    detected_type = detected_audio_content_type(data)
    if not detected_type:
        raise AudioDownloadError(
            f"unrecognized audio signature (declared type {declared_type or 'unknown'})"
        )
    if declared_type and not (
        declared_type.startswith("audio/")
        or declared_type in {"application/ogg", "application/octet-stream"}
    ):
        raise AudioDownloadError(f"unexpected response content type {declared_type!r}")
    return detected_type


def validate_voice_payload(data: bytes, max_bytes: int) -> None:
    if not data:
        raise AudioConversionError("FFmpeg returned an empty voice file")
    if len(data) > max_bytes:
        raise AudioConversionError(
            f"converted voice is larger than the {max_bytes:,}-byte limit"
        )
    if not data.startswith(b"OggS") or b"OpusHead" not in data[:4096]:
        raise AudioConversionError(
            "converted file is not an OGG container encoded with Opus"
        )


def _ffmpeg_executable() -> str:
    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise AudioConversionError(
            "imageio-ffmpeg is not installed; run: uv sync"
        ) from exc
    try:
        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except RuntimeError as exc:
        raise AudioConversionError(f"FFmpeg is unavailable: {exc}") from exc


def transcode_audio_to_voice(
    audio: DownloadedAudio,
    *,
    timeout: float = 30.0,
    max_bytes: int = DEFAULT_MAX_AUDIO_BYTES,
    ffmpeg_executable: str | None = None,
    run: Callable[..., Any] = subprocess.run,
) -> VoiceAudio:
    executable = ffmpeg_executable or _ffmpeg_executable()
    command = [
        executable,
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        "pipe:0",
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "48000",
        "-c:a",
        "libopus",
        "-b:a",
        "32k",
        "-vbr",
        "on",
        "-application",
        "voip",
        "-f",
        "ogg",
        "pipe:1",
    ]
    try:
        result = run(
            command,
            input=audio.data,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise AudioConversionError(
            f"FFmpeg timed out after {timeout:g} seconds"
        ) from exc
    except OSError as exc:
        raise AudioConversionError(f"could not run FFmpeg: {exc}") from exc

    output = bytes(result.stdout or b"")
    if result.returncode != 0:
        details = bytes(result.stderr or b"").decode("utf-8", errors="replace").strip()
        raise AudioConversionError(
            f"FFmpeg failed with exit code {result.returncode}: "
            f"{details[:1000] or 'no error details'}"
        )
    validate_voice_payload(output, max_bytes)
    source_stem = Path(audio.filename or "pronunciation").stem
    return VoiceAudio(
        data=output,
        content_type="audio/ogg",
        filename=f"{source_stem}.voice.ogg",
        sha256=hashlib.sha256(output).hexdigest(),
    )


def download_audio_file(
    source_url: str,
    *,
    timeout: float = 30.0,
    max_bytes: int = DEFAULT_MAX_AUDIO_BYTES,
    urlopen: Callable[..., Any] = urllib.request.urlopen,
) -> DownloadedAudio:
    if urlparse(source_url).scheme not in {"http", "https"}:
        raise AudioDownloadError("audio source URL must use HTTP or HTTPS")

    request = urllib.request.Request(source_url, headers=REQUEST_HEADERS)
    try:
        with urlopen(request, timeout=timeout) as response:
            content_length_text = response.headers.get("Content-Length")
            if content_length_text:
                try:
                    content_length = int(content_length_text)
                except ValueError:
                    content_length = None
                if content_length is not None and content_length > max_bytes:
                    raise AudioDownloadError(
                        f"audio file is larger than the {max_bytes:,}-byte limit"
                    )

            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(min(64 * 1024, max_bytes + 1 - total))
                if not chunk:
                    break
                chunks.append(chunk)
                total += len(chunk)
                if total > max_bytes:
                    raise AudioDownloadError(
                        f"audio file is larger than the {max_bytes:,}-byte limit"
                    )

            data = b"".join(chunks)
            declared_type = declared_content_type(response.headers)
            content_type = validate_audio_payload(data, declared_type)
            filename = filename_from_response(response, source_url)
            status = getattr(response, "status", None)
            return DownloadedAudio(
                data=data,
                content_type=content_type,
                filename=filename,
                sha256=hashlib.sha256(data).hexdigest(),
                http_status=int(status) if status is not None else None,
            )
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise AudioRateLimitError(
                "HTTP 429 Too Many Requests",
                status_code=429,
            ) from exc
        raise AudioDownloadError(
            f"HTTP {exc.code}: {exc.reason}",
            retryable=exc.code in RETRYABLE_HTTP_STATUS,
            status_code=exc.code,
        ) from exc
    except AudioDownloadError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AudioDownloadError(
            f"temporary network error: {exc}",
            retryable=True,
        ) from exc


def download_with_retries(
    source_url: str,
    *,
    timeout: float,
    max_bytes: int,
    retries: int,
    retry_backoff: float,
    fetch_audio: Callable[..., DownloadedAudio] = download_audio_file,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[DownloadedAudio, int]:
    for retry_number in range(retries + 1):
        attempts = retry_number + 1
        try:
            audio = fetch_audio(
                source_url,
                timeout=timeout,
                max_bytes=max_bytes,
            )
            return audio, attempts
        except AudioRateLimitError as exc:
            exc.attempts = attempts
            raise
        except AudioDownloadError as exc:
            exc.attempts = attempts
            if not exc.retryable or retry_number >= retries:
                raise
            delay = retry_backoff * (2**retry_number)
            LOGGER.warning(
                "Temporary audio error: %s; retry %s/%s in %.1f seconds",
                exc,
                retry_number + 1,
                retries,
                delay,
            )
            sleep(delay)
    raise AssertionError("retry loop ended unexpectedly")


def _load_psycopg() -> Any:
    try:
        import psycopg
    except ImportError as exc:
        raise OaldAudioDatabaseError("psycopg is not installed; run: uv sync") from exc
    return psycopg


def load_candidates(
    cursor: Any,
    *,
    dialects: list[str],
    force: bool,
    limit: int | None,
    source_urls: list[str] | None = None,
) -> list[AudioCandidate]:
    sql_limit = limit if limit is not None else 2_147_483_647
    cursor.execute(
        CANDIDATE_SQL,
        (dialects, force, source_urls, source_urls, sql_limit),
    )
    return [
        AudioCandidate(
            source_url=str(row[0]),
            example_word=str(row[1]),
            dialects=tuple(row[2]),
            has_original=bool(row[3]),
        )
        for row in cursor.fetchall()
    ]


def load_stored_audio(cursor: Any, candidate: AudioCandidate) -> DownloadedAudio:
    cursor.execute(LOAD_STORED_AUDIO_SQL, (candidate.source_url,))
    row = cursor.fetchone()
    if row is None:
        raise OaldAudioDatabaseError(
            f"stored audio disappeared for {candidate.source_url}"
        )
    return DownloadedAudio(
        data=bytes(row[0]),
        content_type=str(row[1]),
        filename=str(row[2]),
        sha256=str(row[3]).strip(),
        http_status=int(row[4]) if row[4] is not None else None,
    )


def store_success(
    cursor: Any,
    candidate: AudioCandidate,
    audio: DownloadedAudio,
    attempts: int,
) -> None:
    cursor.execute(
        STORE_SUCCESS_SQL,
        (
            audio.data,
            audio.content_type,
            audio.filename,
            len(audio.data),
            audio.sha256,
            audio.http_status,
            attempts,
            candidate.source_url,
        ),
    )


def store_failure(
    cursor: Any,
    candidate: AudioCandidate,
    error: AudioDownloadError,
    *,
    keep_pending: bool = False,
) -> None:
    cursor.execute(
        STORE_FAILURE_SQL,
        (
            "pending" if keep_pending else "failed",
            error.status_code,
            str(error)[:2000],
            error.attempts,
            candidate.source_url,
        ),
    )


def store_voice_success(
    cursor: Any,
    candidate: AudioCandidate,
    original: DownloadedAudio,
    voice: VoiceAudio,
    *,
    clear_telegram_cache: bool = False,
) -> None:
    cursor.execute(
        STORE_VOICE_SUCCESS_SQL,
        (
            candidate.source_url,
            original.sha256,
            voice.data,
            voice.filename,
            len(voice.data),
            voice.sha256,
        ),
    )
    if clear_telegram_cache:
        cursor.execute(
            """
            DELETE FROM bot_telegram_audio_cache
            WHERE source_url = %s AND send_method = 'voice'
            """,
            (candidate.source_url,),
        )


def store_voice_failure(
    cursor: Any,
    candidate: AudioCandidate,
    original: DownloadedAudio,
    error: AudioConversionError,
) -> None:
    cursor.execute(
        STORE_VOICE_FAILURE_SQL,
        (candidate.source_url, original.sha256, str(error)[:2000]),
    )


def download_audio_to_postgres(
    database_url: str,
    *,
    dialects: list[str] | None = None,
    limit: int | None = None,
    force: bool = False,
    request_delay: float = 0.5,
    timeout: float = 30.0,
    retries: int = 3,
    retry_backoff: float = 2.0,
    max_audio_bytes: int = DEFAULT_MAX_AUDIO_BYTES,
    fail_fast: bool = False,
    source_urls: list[str] | None = None,
    fetch_audio: Callable[..., DownloadedAudio] = download_audio_file,
    transcode_voice: Callable[..., VoiceAudio] = transcode_audio_to_voice,
    sleep: Callable[[float], None] = time.sleep,
) -> DownloadStats:
    psycopg = _load_psycopg()
    selected_dialects = dialects or ["us", "gb"]
    stats = DownloadStats()
    try:
        with psycopg.connect(
            database_url,
            autocommit=True,
            connect_timeout=DEFAULT_CONNECT_TIMEOUT,
            **connection_options(database_url),
        ) as connection:
            with connection.cursor() as cursor:
                require_oald_schema(cursor)
                cursor.execute("SELECT to_regclass('public.bot_telegram_audio_cache')")
                clear_telegram_cache = cursor.fetchone()[0] is not None
                candidates = load_candidates(
                    cursor,
                    dialects=selected_dialects,
                    force=force,
                    limit=limit,
                    source_urls=source_urls,
                )
                stats.candidates = len(candidates)
                LOGGER.info(
                    "Audio candidates=%s dialects=%s force=%s",
                    f"{stats.candidates:,}",
                    ",".join(selected_dialects),
                    force,
                )

                network_requests = 0
                for position, candidate in enumerate(candidates, start=1):
                    needs_download = force or not candidate.has_original
                    LOGGER.info(
                        "[%s/%s] Preparing %s (%s): %s",
                        f"{position:,}",
                        f"{stats.candidates:,}",
                        candidate.example_word,
                        ",".join(candidate.dialects),
                        candidate.source_url,
                    )
                    try:
                        if needs_download:
                            if network_requests and request_delay:
                                sleep(request_delay)
                            network_requests += 1
                            audio, attempts = download_with_retries(
                                candidate.source_url,
                                timeout=timeout,
                                max_bytes=max_audio_bytes,
                                retries=retries,
                                retry_backoff=retry_backoff,
                                fetch_audio=fetch_audio,
                                sleep=sleep,
                            )
                            store_success(cursor, candidate, audio, attempts)
                            stats.downloaded += 1
                            stats.stored_bytes += len(audio.data)
                            LOGGER.info(
                                "Stored original %s: filename=%s bytes=%s type=%s",
                                candidate.example_word,
                                audio.filename,
                                f"{len(audio.data):,}",
                                audio.content_type,
                            )
                        else:
                            audio = load_stored_audio(cursor, candidate)
                            stats.reused_originals += 1
                            LOGGER.info(
                                "Using stored original for %s; no HTTP request",
                                candidate.example_word,
                            )

                        try:
                            voice = transcode_voice(
                                audio,
                                timeout=timeout,
                                max_bytes=max_audio_bytes,
                            )
                            store_voice_success(
                                cursor,
                                candidate,
                                audio,
                                voice,
                                clear_telegram_cache=clear_telegram_cache,
                            )
                            stats.voices_prepared += 1
                            stats.voice_bytes += len(voice.data)
                            LOGGER.info(
                                "Stored Telegram voice for %s: filename=%s bytes=%s",
                                candidate.example_word,
                                voice.filename,
                                f"{len(voice.data):,}",
                            )
                        except AudioConversionError as exc:
                            store_voice_failure(cursor, candidate, audio, exc)
                            stats.conversion_failed += 1
                            LOGGER.error(
                                "Voice conversion failed for %s (%s): %s",
                                candidate.example_word,
                                ",".join(candidate.dialects),
                                exc,
                            )
                            if fail_fast:
                                raise
                    except AudioRateLimitError as exc:
                        store_failure(cursor, candidate, exc, keep_pending=True)
                        stats.rate_limited = True
                        LOGGER.error(
                            "OALD rate limit reached for %s. The run stopped "
                            "without waiting; rerun the same command later.",
                            candidate.example_word,
                        )
                        break
                    except AudioDownloadError as exc:
                        store_failure(cursor, candidate, exc)
                        stats.failed += 1
                        LOGGER.error(
                            "Audio download failed for %s (%s): %s",
                            candidate.example_word,
                            ",".join(candidate.dialects),
                            exc,
                        )
                        if fail_fast:
                            raise
        return stats
    except (AudioDownloadError, AudioConversionError):
        raise
    except psycopg.Error as exc:
        raise OaldAudioDatabaseError(
            "PostgreSQL audio operation failed; verify the database URL and "
            "run import_oald_postgres.py first"
        ) from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("OALD_DATABASE_URL"),
        help="OALD PostgreSQL URL; defaults to OALD_DATABASE_URL",
    )
    parser.add_argument(
        "--dialects",
        nargs="+",
        choices=("us", "gb"),
        default=["us", "gb"],
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


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    configure_logging(args.log_level)
    if not args.database_url:
        LOGGER.error(
            "PostgreSQL URL is required: use --database-url or set OALD_DATABASE_URL"
        )
        return 2

    try:
        stats = download_audio_to_postgres(
            args.database_url,
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


if __name__ == "__main__":
    raise SystemExit(main())
