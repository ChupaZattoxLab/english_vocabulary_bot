"""OALD audio download, transcode, and store helpers."""

from scripts.oald.audio.download import download_audio_file, download_with_retries
from scripts.oald.audio.errors import (
    AudioConversionError,
    AudioDownloadError,
    AudioRateLimitError,
    OaldAudioDatabaseError,
    OaldAudioError,
)
from scripts.oald.audio.models import (
    AudioCandidate,
    DownloadedAudio,
    DownloadStats,
    VoiceAudio,
)
from scripts.oald.audio.run import download_audio_to_postgres, load_candidates
from scripts.oald.audio.transcode import (
    resolve_ffmpeg_executable,
    transcode_audio_to_voice,
    validate_voice_payload,
)

__all__ = [
    "AudioCandidate",
    "AudioConversionError",
    "AudioDownloadError",
    "AudioRateLimitError",
    "DownloadedAudio",
    "DownloadStats",
    "OaldAudioDatabaseError",
    "OaldAudioError",
    "VoiceAudio",
    "download_audio_file",
    "download_audio_to_postgres",
    "download_with_retries",
    "load_candidates",
    "resolve_ffmpeg_executable",
    "transcode_audio_to_voice",
    "validate_voice_payload",
]
