import asyncio
import json
import tempfile
import unittest
import uuid
from pathlib import Path

import sqlalchemy as sa

from scripts.oald.import_oald import (
    OaldValidationError,
    import_entries,
    load_entries,
)
from tests.support import requires_oald_database, run_db, temporary_migrated_database
from tgbot.db.tables import oald_audio_files, oald_entries, oald_entry_audio_sources
from tgbot.db.types import AudioDownloadStatus

ROOT = Path(__file__).resolve().parents[2]


class OaldJsonTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.json_path = Path(self.temporary_directory.name) / "words.json"

    def test_valid_row_preserves_unicode_and_translation_shape(self) -> None:
        row = oald_row(
            "analyze",
            "https://www.oxfordlearnersdictionaries.com/definition/english/analyze",
        )
        row["word_gb"] = "analyse"
        row["translations"]["ru"]["main"] = "анализировать"
        write_rows(self.json_path, [row])

        entries, stats = load_entries(self.json_path, strict=True)

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].word_us, "analyze")
        self.assertEqual(entries[0].word_gb, "analyse")
        self.assertEqual(
            entries[0].translations,
            ["анализировать", "проверка"],
        )
        self.assertEqual(stats["valid_rows"], 1)
        self.assertEqual(stats["unique_audio_urls"], 2)

    def test_two_lie_verb_senses_are_distinguished_by_oxford_url(self) -> None:
        rows = [
            oald_row(
                "lie",
                "https://www.oxfordlearnersdictionaries.com/definition/english/lie1_1",
                definition="To rest horizontally.",
            ),
            oald_row(
                "lie",
                "https://www.oxfordlearnersdictionaries.com/definition/english/lie2_1",
                definition="To say something untrue.",
            ),
        ]
        write_rows(self.json_path, rows)

        entries, _ = load_entries(self.json_path, strict=True)

        self.assertEqual(len(entries), 2)
        self.assertEqual(
            {entry.definition for entry in entries},
            {"To rest horizontally.", "To say something untrue."},
        )

    def test_duplicate_audio_urls_are_counted_once(self) -> None:
        shared = "https://audio.example/shared.ogg"
        rows = [
            oald_row(
                "first",
                "https://dictionary.example/first",
                audio_us=[shared],
                audio_gb=[],
            ),
            oald_row(
                "second",
                "https://dictionary.example/second",
                audio_us=[shared],
                audio_gb=[],
            ),
        ]
        write_rows(self.json_path, rows)

        entries, stats = load_entries(self.json_path, strict=True)

        self.assertEqual(len(entries), 2)
        self.assertEqual(stats["audio_references_us"], 2)
        self.assertEqual(stats["unique_audio_urls"], 1)

    def test_mature_mismatched_ipa_and_audio_arrays_are_preserved(self) -> None:
        row = oald_row(
            "mature",
            "https://www.oxfordlearnersdictionaries.com/definition/english/mature_1",
            lexical_category="adjective",
            ipa_gb=["/məˈtʃʊə(r)/", "/məˈtʃɔː(r)/"],
            audio_gb=["https://audio.example/mature-gb.ogg"],
        )
        write_rows(self.json_path, [row])

        entries, _ = load_entries(self.json_path, strict=True)

        self.assertEqual(
            entries[0].ipa_gb,
            ["/məˈtʃʊə(r)/", "/məˈtʃɔː(r)/"],
        )
        self.assertEqual(
            entries[0].audio_source_gb,
            ["https://audio.example/mature-gb.ogg"],
        )

    def test_invalid_row_is_skipped_or_raises_in_strict_mode(self) -> None:
        row = oald_row("invalid", "https://dictionary.example/invalid")
        row["cefr"] = "z9"
        write_rows(self.json_path, [row])

        entries, stats = load_entries(self.json_path)
        self.assertEqual(entries, [])
        self.assertEqual(stats["invalid_rows"], 1)

        with self.assertRaises(OaldValidationError):
            load_entries(self.json_path, strict=True)

    def test_current_dataset_matches_expected_counts(self) -> None:
        dataset_path = ROOT / "data" / "oald" / "words.json"
        if not dataset_path.exists():
            self.skipTest("private OALD dataset is not available")
        entries, stats = load_entries(dataset_path, strict=True)

        self.assertEqual(len(entries), 5906)
        self.assertEqual(stats["audio_references_us"], 6120)
        self.assertEqual(stats["audio_references_gb"], 6139)
        self.assertEqual(stats["unique_audio_urls"], 10393)


@requires_oald_database
class OaldPostgreSqlIntegrationTests(unittest.TestCase):
    db_url: str

    @classmethod
    def setUpClass(cls) -> None:
        cls._db = temporary_migrated_database(prefix="oald_import_")
        cls.db_url = cls._db.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._db.__exit__(None, None, None)

    def test_repeat_add_update_links_and_preserve_audio_bytes(self) -> None:
        suffix = uuid.uuid4().hex
        first_definition_url = f"https://dictionary.example/{suffix}/lie1"
        second_definition_url = f"https://dictionary.example/{suffix}/lie2"
        added_definition_url = f"https://dictionary.example/{suffix}/added"
        first_audio_url = f"https://audio.example/{suffix}/shared.ogg"
        changed_audio_url = f"https://audio.example/{suffix}/changed.ogg"
        all_definition_urls = [
            first_definition_url,
            second_definition_url,
            added_definition_url,
        ]
        all_audio_urls = [first_audio_url, changed_audio_url]

        with tempfile.TemporaryDirectory() as temporary_directory:
            json_path = Path(temporary_directory) / "words.json"
            first = oald_row(
                f"lie-{suffix}",
                first_definition_url,
                audio_us=[first_audio_url],
                audio_gb=[],
            )
            second = oald_row(
                f"lie-{suffix}",
                second_definition_url,
                audio_us=[first_audio_url],
                audio_gb=[],
            )
            rows = [first, second]

            try:
                write_rows(json_path, rows)
                entries, _ = load_entries(json_path, strict=True)
                self.assertEqual(
                    asyncio.run(import_entries(entries, self.db_url)).entries,
                    2,
                )
                self.assertEqual(
                    asyncio.run(import_entries(entries, self.db_url)).entries,
                    2,
                )

                async def mark_downloaded(connection) -> None:
                    await connection.execute(
                        sa.update(oald_audio_files)
                        .where(oald_audio_files.c.source_url == first_audio_url)
                        .values(
                            audio_data=b"OggS-stored",
                            download_status=AudioDownloadStatus.DOWNLOADED,
                            size_bytes=len(b"OggS-stored"),
                        )
                    )

                run_db(self.db_url, mark_downloaded)

                first["definition"] = "An updated definition."
                first["audio_source_us"] = [changed_audio_url]
                rows.append(
                    oald_row(
                        f"added-{suffix}",
                        added_definition_url,
                        lexical_category="noun",
                        audio_us=[changed_audio_url],
                        audio_gb=[],
                    )
                )
                write_rows(json_path, rows)
                updated_entries, _ = load_entries(json_path, strict=True)
                result = asyncio.run(import_entries(updated_entries, self.db_url))
                self.assertEqual(result.entries, 3)
                self.assertEqual(result.unique_audio_urls, 2)

                async def read_import(connection) -> None:
                    definition = (
                        await connection.execute(
                            sa.select(oald_entries.c.definition).where(
                                oald_entries.c.definition_url_oxford
                                == first_definition_url
                            )
                        )
                    ).scalar_one()
                    self.assertEqual(definition, "An updated definition.")
                    stored_count = (
                        await connection.execute(
                            sa.select(sa.func.count())
                            .select_from(oald_entries)
                            .where(
                                oald_entries.c.definition_url_oxford.in_(
                                    all_definition_urls
                                )
                            )
                        )
                    ).scalar_one()
                    self.assertEqual(stored_count, 3)
                    audio_data = (
                        await connection.execute(
                            sa.select(oald_audio_files.c.audio_data).where(
                                oald_audio_files.c.source_url == first_audio_url
                            )
                        )
                    ).scalar_one()
                    self.assertEqual(bytes(audio_data), b"OggS-stored")

                run_db(self.db_url, read_import)
            finally:

                async def cleanup(connection) -> None:
                    await connection.execute(
                        sa.delete(oald_entries).where(
                            oald_entries.c.definition_url_oxford.in_(
                                all_definition_urls
                            )
                        )
                    )
                    await connection.execute(
                        sa.delete(oald_audio_files).where(
                            oald_audio_files.c.source_url.in_(all_audio_urls),
                            ~sa.exists(
                                sa.select(sa.literal(1)).where(
                                    oald_entry_audio_sources.c.source_url
                                    == oald_audio_files.c.source_url
                                )
                            ),
                        )
                    )

                run_db(self.db_url, cleanup)


def oald_row(
    word: str,
    definition_url: str,
    lexical_category: str = "verb",
    cefr: str = "b1",
    definition: str = "A test definition.",
    example: str = "A test example.",
    ipa_us: list[str] | None = None,
    ipa_gb: list[str] | None = None,
    audio_us: list[str] | None = None,
    audio_gb: list[str] | None = None,
) -> dict:
    return {
        "word_us": word,
        "word_gb": word,
        "lexical_category": lexical_category,
        "cefr": cefr,
        "definition_url_oxford": definition_url,
        "definition_url_cambridge": f"https://dictionary.example/{word}",
        "ipa_us": ipa_us if ipa_us is not None else ["/test/"],
        "ipa_gb": ipa_gb if ipa_gb is not None else ["/test/"],
        "definition": definition,
        "example": example,
        "audio_source_us": (
            audio_us
            if audio_us is not None
            else [f"https://audio.example/{word}-us.ogg"]
        ),
        "audio_source_gb": (
            audio_gb
            if audio_gb is not None
            else [f"https://audio.example/{word}-gb.ogg"]
        ),
        "translations": {
            "ru": {
                "main": "тест",
                "also": ["проверка"],
            }
        },
    }


def write_rows(path: Path, rows: list[dict]) -> None:
    path.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
