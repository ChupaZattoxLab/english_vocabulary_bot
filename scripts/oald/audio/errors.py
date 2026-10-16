"""Errors for OALD audio processing."""


class OaldAudioError(RuntimeError):
    """Base error for OALD audio processing."""


class OaldAudioDatabaseError(OaldAudioError):
    """Raised when PostgreSQL audio access fails."""


class AudioDownloadError(OaldAudioError):
    """Raised when one audio file cannot be downloaded or validated."""

    def __init__(
        self,
        message: str,
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
