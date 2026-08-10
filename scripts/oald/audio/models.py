"""Domain models for OALD audio download."""

from __future__ import annotations

from dataclasses import dataclass


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
