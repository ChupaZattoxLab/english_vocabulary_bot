"""HTTP download helpers for OALD pronunciation audio."""

from __future__ import annotations

import hashlib
import logging
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from scripts.oald.audio.constants import (
    DEFAULT_MAX_AUDIO_BYTES,
    REQUEST_HEADERS,
    RETRYABLE_HTTP_STATUS,
)
from scripts.oald.audio.errors import AudioDownloadError, AudioRateLimitError
from scripts.oald.audio.models import DownloadedAudio

LOGGER = logging.getLogger("tgbot.oald_audio_download")


def download_audio_file(
    source_url: str,
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
