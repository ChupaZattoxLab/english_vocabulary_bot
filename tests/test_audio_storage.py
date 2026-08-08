import csv
import hashlib
import os
import sys
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

if (
    not (ROOT / "scripts" / "download_audio.py").is_file()
    or not (ROOT / "scripts" / "import_postgres.py").is_file()
):
    raise unittest.SkipTest(
        "legacy download_audio.py/import_postgres.py scripts are not present"
    )

from download_audio import (  # noqa: E402
    AudioDownloadError,
    AudioFile,
    download_audio_file,
    download_audio_to_postgres,
    filename_from_url,
)
from import_postgres import CSV_COLUMNS, import_csv_to_postgres  # noqa: E402


class FakeHeaders:
    def __init__(self, content_type: str, content_length: int | None = None):
        self.content_type = content_type
        self.content_length = content_length

    def get(self, name: str, default=None):
        if name.lower() == "content-length" and self.content_length is not None:
            return str(self.content_length)
        return default

    def get_content_type(self) -> str:
        return self.content_type


class FakeResponse:
    def __init__(self, data: bytes, content_type: str = "audio/ogg"):
        self.data = data
        self.offset = 0
        self.headers = FakeHeaders(content_type, len(data))

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, size: int) -> bytes:
        chunk = self.data[self.offset : self.offset + size]
        self.offset += len(chunk)
        return chunk

    def geturl(self) -> str:
        return "https://upload.wikimedia.org/example.ogg"


def vocabulary_row(word: str, audio_url: str) -> dict[str, str]:
    return {
        "word": word,
        "cefr": "A1",
        "part_of_speech": "noun",
        "definition": "A test definition.",
        "example": "This is a test example.",
        "phonetic": "/test/",
        "audio_url": audio_url,
        "source_url": f"https://en.wiktionary.org/wiki/{word}",
    }


def write_vocabulary_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


class AudioDownloadTests(unittest.TestCase):
    def test_filename_is_read_from_commons_redirect_url(self) -> None:
        url = (
            "https://commons.wikimedia.org/wiki/Special:Redirect/file/"
            "en-us-test%20word.ogg"
        )
        self.assertEqual(filename_from_url(url), "en-us-test word.ogg")

    @patch("urllib.request.urlopen")
    def test_audio_bytes_and_metadata_are_collected(self, urlopen) -> None:
        content = b"OggS-test-audio"
        urlopen.return_value = FakeResponse(content)

        audio = download_audio_file(
            "https://example.test/en-us-color.ogg",
            max_bytes=1_000,
        )

        self.assertEqual(audio.data, content)
        self.assertEqual(audio.content_type, "audio/ogg")
        self.assertEqual(audio.filename, "en-us-color.ogg")
        self.assertEqual(audio.sha256, hashlib.sha256(content).hexdigest())

    @patch("urllib.request.urlopen")
    def test_file_larger_than_limit_is_rejected(self, urlopen) -> None:
        urlopen.return_value = FakeResponse(b"x" * 20)

        with self.assertRaisesRegex(AudioDownloadError, "larger than"):
            download_audio_file(
                "https://example.test/audio.ogg",
                max_bytes=10,
            )

    def test_non_http_url_is_rejected(self) -> None:
        with self.assertRaisesRegex(AudioDownloadError, "HTTP or HTTPS"):
            download_audio_file("file:///tmp/audio.ogg")


@unittest.skipUnless(
    os.environ.get("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is not set",
)
class AudioStorageIntegrationTests(unittest.TestCase):
    database_url = os.environ.get("TEST_DATABASE_URL", "")

    def test_audio_is_stored_skipped_and_cleared_when_url_changes(self) -> None:
        try:
            import psycopg
        except ImportError as exc:
            self.skipTest(f"psycopg is not installed: {exc}")

        word = f"audio-integration-{uuid.uuid4().hex}"
        first_url = "https://example.test/first.ogg"
        second_url = "https://example.test/second.ogg"
        audio_bytes = b"OggS-integration-audio"
        fake_audio = AudioFile(
            data=audio_bytes,
            content_type="audio/ogg",
            filename="first.ogg",
            sha256=hashlib.sha256(audio_bytes).hexdigest(),
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            csv_path = Path(temporary_directory) / "audio.csv"
            try:
                write_vocabulary_csv(csv_path, [vocabulary_row(word, first_url)])
                import_csv_to_postgres(csv_path, self.database_url)

                attempts = 0

                def flaky_fetch(*args, **kwargs):
                    nonlocal attempts
                    attempts += 1
                    if attempts == 1:
                        raise AudioDownloadError("temporary", retryable=True)
                    return fake_audio

                with patch("download_audio.time.sleep") as sleep:
                    with self.assertLogs(
                        "vocabulary.audio_download", level="WARNING"
                    ) as retry_logs:
                        first_stats = download_audio_to_postgres(
                            self.database_url,
                            word=word,
                            retries=1,
                            retry_backoff=0.1,
                            fetch_audio=flaky_fetch,
                        )
                second_stats = download_audio_to_postgres(
                    self.database_url,
                    word=word,
                    fetch_audio=lambda *args, **kwargs: fake_audio,
                )

                self.assertEqual(first_stats.downloaded, 1)
                self.assertEqual(attempts, 2)
                sleep.assert_called_once_with(0.1)
                self.assertIn("retry 1/1", retry_logs.output[0])
                self.assertEqual(second_stats.candidates, 0)

                with psycopg.connect(self.database_url) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT audio_data, audio_content_type, audio_filename,
                                   audio_size_bytes, audio_sha256,
                                   audio_file_source_url, audio_downloaded_at
                            FROM vocabulary_entries
                            WHERE word = %s AND part_of_speech = 'noun'
                            """,
                            (word,),
                        )
                        stored = cursor.fetchone()

                self.assertEqual(bytes(stored[0]), audio_bytes)
                self.assertEqual(stored[1], "audio/ogg")
                self.assertEqual(stored[2], "first.ogg")
                self.assertEqual(stored[3], len(audio_bytes))
                self.assertEqual(stored[4].strip(), fake_audio.sha256)
                self.assertEqual(stored[5], first_url)
                self.assertIsNotNone(stored[6])

                write_vocabulary_csv(csv_path, [vocabulary_row(word, second_url)])
                import_csv_to_postgres(csv_path, self.database_url)

                with psycopg.connect(self.database_url) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT audio_url, audio_data, audio_filename,
                                   audio_file_source_url, audio_downloaded_at
                            FROM vocabulary_entries
                            WHERE word = %s AND part_of_speech = 'noun'
                            """,
                            (word,),
                        )
                        changed = cursor.fetchone()

                self.assertEqual(changed[0], second_url)
                self.assertIsNone(changed[1])
                self.assertEqual(changed[2], "")
                self.assertEqual(changed[3], "")
                self.assertIsNone(changed[4])
            finally:
                with psycopg.connect(self.database_url) as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "DELETE FROM vocabulary_entries WHERE word = %s",
                            (word,),
                        )


if __name__ == "__main__":
    unittest.main()
