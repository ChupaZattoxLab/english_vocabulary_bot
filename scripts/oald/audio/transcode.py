"""FFmpeg transcoding to Telegram voice (OGG Opus)."""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts.oald.audio.constants import DEFAULT_MAX_AUDIO_BYTES
from scripts.oald.audio.errors import AudioConversionError
from scripts.oald.audio.models import DownloadedAudio, VoiceAudio


def transcode_audio_to_voice(
    audio: DownloadedAudio,
    timeout: float = 30.0,
    max_bytes: int = DEFAULT_MAX_AUDIO_BYTES,
    ffmpeg_executable: str | None = None,
    run: Callable[..., Any] = subprocess.run,
) -> VoiceAudio:
    executable = ffmpeg_executable or resolve_ffmpeg_executable()
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


def resolve_ffmpeg_executable() -> str:
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
