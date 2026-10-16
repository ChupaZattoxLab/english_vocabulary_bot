"""Shared constants for OALD audio download."""

DEFAULT_MAX_AUDIO_BYTES = 10 * 1024 * 1024
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
