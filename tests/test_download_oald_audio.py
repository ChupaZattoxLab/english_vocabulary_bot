import hashlib
import io
import os
import sys
import tempfile
import unittest
import urllib.error
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "build_database"))

from download_oald_audio import (  # noqa: E402
    AudioConversionError,
    AudioDownloadError,
    AudioRateLimitError,
    DownloadedAudio,
    VoiceAudio,
    download_audio_file,
    download_audio_to_postgres,
    download_with_retries,
    transcode_audio_to_voice,
    validate_voice_payload,
)
from import_oald_postgres import import_entries, load_entries  # noqa: E402
from test_import_oald_postgres import oald_row, write_rows  # noqa: E402


class FakeHeaders:
    def __init__(
        self,
        content_type: str = "audio/ogg",
        content_length: int | None = None,
        content_disposition: str = "",
    ):
        self.content_type = content_type
        self.content_length = content_length
        self.content_disposition = content_disposition

    def get(self, name: str, default=None):
        normalized = name.lower()
        if normalized == "content-length" and self.content_length is not None:
            return str(self.content_length)
        if normalized == "content-type":
            return self.content_type
        if normalized == "content-disposition" and self.content_disposition:
            return self.content_disposition
        return default

    def get_content_type(self) -> str:
        return self.content_type


class FakeResponse:
    def __init__(
        self,
        data: bytes,
        *,
        content_type: str = "audio/ogg",
        url: str = "https://audio.example/test.ogg",
        content_length: int | None = None,
    ):
        self.stream = io.BytesIO(data)
        self.headers = FakeHeaders(
            content_type,
            len(data) if content_length is None else content_length,
        )
        self.url = url
        self.status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, size: int) -> bytes:
        return self.stream.read(size)

    def geturl(self) -> str:
        return self.url


class OaldAudioDownloadTests(unittest.TestCase):
    def test_voice_payload_requires_ogg_opus(self) -> None:
        validate_voice_payload(b"OggS-header-OpusHead-audio", 1000)
        with self.assertRaisesRegex(AudioConversionError, "encoded with Opus"):
            validate_voice_payload(b"OggS-header-vorbis-audio", 1000)

    def test_transcode_builds_mono_opus_voice(self) -> None:
        output = b"OggS-header-OpusHead-voice"
        runner = Mock(
            return_value=SimpleNamespace(returncode=0, stdout=output, stderr=b"")
        )
        original = DownloadedAudio(
            data=b"OggS-original",
            content_type="audio/ogg",
            filename="color_us.ogg",
            sha256=hashlib.sha256(b"OggS-original").hexdigest(),
        )

        voice = transcode_audio_to_voice(
            original,
            ffmpeg_executable="ffmpeg-test",
            run=runner,
        )

        command = runner.call_args.args[0]
        self.assertIn("libopus", command)
        self.assertEqual(command[command.index("-ac") + 1], "1")
        self.assertEqual(command[command.index("-ar") + 1], "48000")
        self.assertEqual(voice.data, output)
        self.assertEqual(voice.filename, "color_us.voice.ogg")
        self.assertEqual(voice.content_type, "audio/ogg")

    def test_transcode_reports_ffmpeg_failure(self) -> None:
        runner = Mock(
            return_value=SimpleNamespace(
                returncode=1,
                stdout=b"",
                stderr=b"invalid input",
            )
        )
        original = DownloadedAudio(
            data=b"invalid",
            content_type="audio/ogg",
            filename="bad.ogg",
            sha256=hashlib.sha256(b"invalid").hexdigest(),
        )

        with self.assertRaisesRegex(AudioConversionError, "invalid input"):
            transcode_audio_to_voice(
                original,
                ffmpeg_executable="ffmpeg-test",
                run=runner,
            )

    def test_valid_ogg_is_downloaded_and_hashed(self) -> None:
        payload = b"OggS-test-pronunciation"
        audio = download_audio_file(
            "https://audio.example/color.ogg",
            max_bytes=1000,
            urlopen=lambda *args, **kwargs: FakeResponse(
                payload,
                url="https://cdn.example/color-us.ogg",
            ),
        )

        self.assertEqual(audio.data, payload)
        self.assertEqual(audio.content_type, "audio/ogg")
        self.assertEqual(audio.filename, "color-us.ogg")
        self.assertEqual(audio.sha256, hashlib.sha256(payload).hexdigest())

    def test_declared_large_file_is_rejected_before_reading(self) -> None:
        with self.assertRaisesRegex(AudioDownloadError, "larger than"):
            download_audio_file(
                "https://audio.example/large.ogg",
                max_bytes=10,
                urlopen=lambda *args, **kwargs: FakeResponse(
                    b"OggS-audio",
                    content_length=100,
                ),
            )

    def test_html_response_is_rejected(self) -> None:
        with self.assertRaisesRegex(AudioDownloadError, "HTML"):
            download_audio_file(
                "https://audio.example/not-audio.ogg",
                urlopen=lambda *args, **kwargs: FakeResponse(
                    b"<!doctype html><html>blocked</html>",
                    content_type="text/html",
                ),
            )

    def test_temporary_error_is_retried(self) -> None:
        calls = 0
        sleeps: list[float] = []

        def fetch(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise AudioDownloadError("temporary", retryable=True)
            return DownloadedAudio(
                data=b"OggS-ok",
                content_type="audio/ogg",
                filename="ok.ogg",
                sha256=hashlib.sha256(b"OggS-ok").hexdigest(),
            )

        audio, attempts = download_with_retries(
            "https://audio.example/retry.ogg",
            timeout=1,
            max_bytes=1000,
            retries=1,
            retry_backoff=0.25,
            fetch_audio=fetch,
            sleep=sleeps.append,
        )

        self.assertEqual(audio.filename, "ok.ogg")
        self.assertEqual(attempts, 2)
        self.assertEqual(sleeps, [0.25])

    def test_http_429_stops_without_retry_sleep(self) -> None:
        sleeps: list[float] = []
        http_error = urllib.error.HTTPError(
            "https://audio.example/rate.ogg",
            429,
            "Too Many Requests",
            {},
            None,
        )

        def fetch(*args, **kwargs):
            raise AudioRateLimitError(
                "HTTP 429 Too Many Requests",
                status_code=http_error.code,
            )

        with self.assertRaises(AudioRateLimitError) as raised:
            download_with_retries(
                "https://audio.example/rate.ogg",
                timeout=1,
                max_bytes=1000,
                retries=3,
                retry_backoff=600,
                fetch_audio=fetch,
                sleep=sleeps.append,
            )

        self.assertEqual(raised.exception.attempts, 1)
        self.assertEqual(sleeps, [])

    def test_download_audio_file_converts_http_429(self) -> None:
        def raise_429(*args, **kwargs):
            raise urllib.error.HTTPError(
                "https://audio.example/rate.ogg",
                429,
                "Too Many Requests",
                {},
                None,
            )

        with self.assertRaises(AudioRateLimitError):
            download_audio_file(
                "https://audio.example/rate.ogg",
                urlopen=raise_429,
            )


@unittest.skipUnless(
    os.environ.get("TEST_OALD_DATABASE_URL"),
    "TEST_OALD_DATABASE_URL is not set",
)
class OaldAudioPostgreSqlIntegrationTests(unittest.TestCase):
    database_url = os.environ.get("TEST_OALD_DATABASE_URL", "")

    def test_download_store_skip_and_force(self) -> None:
        try:
            import psycopg
        except ImportError as exc:
            self.skipTest(f"psycopg is not installed: {exc}")

        suffix = uuid.uuid4().hex
        definition_url = f"https://dictionary.example/{suffix}"
        audio_url = f"https://audio.example/{suffix}.ogg"
        payload = b"OggS-integration-audio"
        fetched_audio = DownloadedAudio(
            data=payload,
            content_type="audio/ogg",
            filename=f"{suffix}.ogg",
            sha256=hashlib.sha256(payload).hexdigest(),
            http_status=200,
        )
        fetch = Mock(return_value=fetched_audio)
        voice_payload = b"OggS-integration-OpusHead-voice"
        prepared_voice = VoiceAudio(
            data=voice_payload,
            content_type="audio/ogg",
            filename=f"{suffix}.voice.ogg",
            sha256=hashlib.sha256(voice_payload).hexdigest(),
        )
        transcode = Mock(return_value=prepared_voice)

        with tempfile.TemporaryDirectory() as temporary_directory:
            json_path = Path(temporary_directory) / "words.json"
            write_rows(
                json_path,
                [
                    oald_row(
                        f"audio-{suffix}",
                        definition_url,
                        audio_us=[audio_url],
                        audio_gb=[],
                    )
                ],
            )
            entries, _ = load_entries(json_path, strict=True)

            try:
                import_entries(entries, self.database_url)
                first = download_audio_to_postgres(
                    self.database_url,
                    dialects=["us"],
                    source_urls=[audio_url],
                    request_delay=0,
                    retries=0,
                    fetch_audio=fetch,
                    transcode_voice=transcode,
                    sleep=lambda _: None,
                )
                with psycopg.connect(self.database_url) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "DELETE FROM oald_audio_variants WHERE source_url = %s",
                            (audio_url,),
                        )
                backfill = download_audio_to_postgres(
                    self.database_url,
                    dialects=["us"],
                    source_urls=[audio_url],
                    request_delay=0,
                    retries=0,
                    fetch_audio=fetch,
                    transcode_voice=transcode,
                    sleep=lambda _: None,
                )
                second = download_audio_to_postgres(
                    self.database_url,
                    dialects=["us"],
                    source_urls=[audio_url],
                    request_delay=0,
                    retries=0,
                    fetch_audio=fetch,
                    transcode_voice=transcode,
                    sleep=lambda _: None,
                )
                forced = download_audio_to_postgres(
                    self.database_url,
                    dialects=["us"],
                    source_urls=[audio_url],
                    request_delay=0,
                    retries=0,
                    force=True,
                    limit=1,
                    fetch_audio=fetch,
                    transcode_voice=transcode,
                    sleep=lambda _: None,
                )

                self.assertEqual(first.downloaded, 1)
                self.assertEqual(first.voices_prepared, 1)
                self.assertEqual(backfill.downloaded, 0)
                self.assertEqual(backfill.reused_originals, 1)
                self.assertEqual(backfill.voices_prepared, 1)
                self.assertEqual(second.candidates, 0)
                self.assertEqual(forced.downloaded, 1)
                self.assertEqual(fetch.call_count, 2)
                self.assertEqual(transcode.call_count, 3)

                with psycopg.connect(self.database_url) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT audio_data, content_type, filename, size_bytes,
                                   sha256, download_status, attempt_count
                            FROM oald_audio_files
                            WHERE source_url = %s
                            """,
                            (audio_url,),
                        )
                        stored = cursor.fetchone()
                        cursor.execute(
                            """
                            SELECT audio_data, content_type, filename, size_bytes,
                                   sha256, source_sha256, conversion_status,
                                   attempt_count
                            FROM oald_audio_variants
                            WHERE source_url = %s
                              AND variant_type = 'telegram_voice_opus'
                            """,
                            (audio_url,),
                        )
                        stored_voice = cursor.fetchone()

                self.assertEqual(bytes(stored[0]), payload)
                self.assertEqual(stored[1], "audio/ogg")
                self.assertEqual(stored[2], f"{suffix}.ogg")
                self.assertEqual(stored[3], len(payload))
                self.assertEqual(stored[4].strip(), fetched_audio.sha256)
                self.assertEqual(stored[5], "downloaded")
                self.assertEqual(stored[6], 2)
                self.assertEqual(bytes(stored_voice[0]), voice_payload)
                self.assertEqual(stored_voice[1], "audio/ogg")
                self.assertEqual(stored_voice[2], f"{suffix}.voice.ogg")
                self.assertEqual(stored_voice[3], len(voice_payload))
                self.assertEqual(stored_voice[4].strip(), prepared_voice.sha256)
                self.assertEqual(stored_voice[5].strip(), fetched_audio.sha256)
                self.assertEqual(stored_voice[6], "prepared")
                self.assertEqual(stored_voice[7], 2)
            finally:
                with psycopg.connect(self.database_url) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            DELETE FROM oald_entries
                            WHERE definition_url_oxford = %s
                            """,
                            (definition_url,),
                        )
                        cursor.execute(
                            """
                            DELETE FROM oald_audio_files
                            WHERE source_url = %s
                              AND NOT EXISTS (
                                  SELECT 1
                                  FROM oald_entry_audio_sources
                                  WHERE oald_entry_audio_sources.source_url =
                                        oald_audio_files.source_url
                              )
                            """,
                            (audio_url,),
                        )


if __name__ == "__main__":
    unittest.main()
