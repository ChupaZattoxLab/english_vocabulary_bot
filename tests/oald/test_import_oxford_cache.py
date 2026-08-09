import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path

from import_oxford_cache import (
    OxfordCacheError,
    build_rows,
    import_rows,
    load_definition_index,
    parse_cache_files,
)

from tgbot.db.sync import sync_connection


class OxfordCacheParserTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.directory = Path(self.temporary_directory.name)
        self.cache_directory = self.directory / "cache"
        self.cache_directory.mkdir()
        self.words_json = self.directory / "words.json"

    def build(self, definitions: list[dict]):
        write_json(self.words_json, definitions)
        groups, file_stats = parse_cache_files(self.cache_directory)
        rows, row_stats = build_rows(
            groups,
            load_definition_index(self.words_json),
        )
        return rows, file_stats, row_stats

    def test_homographs_are_merged_with_all_unique_translations(self) -> None:
        entries = [
            {
                "pronunciations": [
                    pronunciation(
                        "ˈan(ə)lʌɪz",
                        "British English",
                        "https://example.test/analyse-gb.mp3",
                    ),
                    pronunciation(
                        "ˈænlˌaɪz",
                        "American English",
                        "https://example.test/analyze-us.mp3",
                    ),
                ],
                "variantForms": [{"text": "analyze", "regions": [{"id": "us"}]}],
                "senses": [
                    {
                        "translations": [
                            translation("анализировать"),
                            translation("analyse", "en"),
                        ],
                        "subsenses": [{"translations": [translation("разбирать")]}],
                    }
                ],
            },
            {
                "pronunciations": [
                    pronunciation(
                        "ˈænlˌaɪz",
                        "American English",
                        "https://example.test/analyze-us.mp3",
                    )
                ],
                "senses": [
                    {
                        "translations": [
                            translation("анализировать"),
                            translation("изучать"),
                        ]
                    }
                ],
            },
        ]
        write_json(
            self.cache_directory / "analyse.json",
            cache_wrapper("analyse", [lexical_entry("analyse", "verb", entries)]),
        )

        rows, file_stats, row_stats = self.build(
            [
                {
                    "word": "analyse",
                    "pos": "verb",
                    "phonetic": "/ˈænlˌaɪz/",
                    "definition": "To examine something carefully.",
                    "example": "We analysed the results.",
                }
            ]
        )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.source_lexical_key, "oxford:analyse:verb")
        self.assertEqual(row.word_us, "analyze")
        self.assertEqual(row.word_gb, "analyse")
        self.assertEqual(row.lexical_category, "verb")
        self.assertEqual(row.ipa_us, ["/ˈænlˌaɪz/"])
        self.assertEqual(
            row.audio_source_us,
            ["https://example.test/analyze-us.mp3"],
        )
        self.assertEqual(row.translations, ["анализировать", "разбирать", "изучать"])
        self.assertEqual(row.definition, "To examine something carefully.")
        self.assertEqual(file_stats["multi_entry_groups"], 1)
        self.assertEqual(row_stats["with_translations"], 1)

    def test_regional_variant_pronunciation_keeps_empty_audio_placeholder(self) -> None:
        entry = {
            "pronunciations": [
                pronunciation(
                    "al(j)ʊˈmɪnɪəm",
                    "British English",
                    "https://example.test/aluminium-gb.mp3",
                )
            ],
            "variantForms": [
                {
                    "text": "aluminum",
                    "regions": [{"id": "us", "text": "Us"}],
                    "pronunciations": [
                        {
                            "phoneticNotation": "IPA",
                            "phoneticSpelling": "əˈluːmɪnəm",
                        }
                    ],
                }
            ],
            "senses": [{"translations": [translation("алюминий")]}],
        }
        write_json(
            self.cache_directory / "aluminium.json",
            cache_wrapper(
                "aluminium",
                [lexical_entry("aluminium", "noun", [entry])],
            ),
        )

        rows, _, _ = self.build([])

        self.assertEqual(rows[0].word_us, "aluminum")
        self.assertEqual(rows[0].word_gb, "aluminium")
        self.assertEqual(rows[0].ipa_us, ["/əˈluːmɪnəm/"])
        self.assertEqual(rows[0].audio_source_us, [""])
        self.assertEqual(len(rows[0].ipa_us), len(rows[0].audio_source_us))

    def test_nonregional_variant_does_not_change_us_or_gb_spelling(self) -> None:
        entry = {
            "pronunciations": [
                pronunciation("ˈenibɒdi", "British English"),
                pronunciation("ˈeniˌbɑdi", "American English"),
            ],
            "variantForms": [
                {
                    "text": "anyone",
                    "pronunciations": [
                        {"phoneticNotation": "IPA", "phoneticSpelling": "ˈeniˌwʌn"}
                    ],
                }
            ],
            "senses": [{"translations": [translation("кто-нибудь")]}],
        }
        write_json(
            self.cache_directory / "anybody.json",
            cache_wrapper(
                "anybody",
                [lexical_entry("anybody", "pronoun", [entry])],
            ),
        )

        rows, _, _ = self.build([])

        self.assertEqual(rows[0].word_us, "anybody")
        self.assertEqual(rows[0].word_gb, "anybody")
        self.assertEqual(rows[0].ipa_us, ["/ˈeniˌbɑdi/"])
        self.assertEqual(rows[0].ipa_gb, ["/ˈenibɒdi/"])

    def test_ambiguous_definition_is_left_empty(self) -> None:
        entry = {
            "pronunciations": [
                pronunciation("laɪ", "British English"),
                pronunciation("laɪ", "American English"),
            ],
            "senses": [{"translations": [translation("лежать")]}],
        }
        write_json(
            self.cache_directory / "lie.json",
            cache_wrapper("lie", [lexical_entry("lie", "verb", [entry])]),
        )
        definitions = [
            {
                "word": "lie",
                "pos": "verb",
                "phonetic": "/laɪ/",
                "definition": "To rest horizontally.",
                "example": "Lie down.",
            },
            {
                "word": "lie",
                "pos": "verb",
                "phonetic": "/laɪ/",
                "definition": "To say something untrue.",
                "example": "Do not lie.",
            },
        ]

        with self.assertLogs("tgbot.oxford_import", level="WARNING"):
            rows, _, row_stats = self.build(definitions)

        self.assertEqual(rows[0].definition, "")
        self.assertEqual(rows[0].example, "")
        self.assertEqual(row_stats["definition_ambiguous"], 1)

    def test_malformed_json_is_skipped_or_raised_in_strict_mode(self) -> None:
        (self.cache_directory / "bad.json").write_text("{bad", encoding="utf-8")

        with self.assertLogs("tgbot.oxford_import", level="ERROR"):
            groups, stats = parse_cache_files(self.cache_directory)
        self.assertEqual(groups, {})
        self.assertEqual(stats["invalid_files"], 1)

        with self.assertRaises(OxfordCacheError):
            parse_cache_files(self.cache_directory, strict=True)


@unittest.skipUnless(
    os.environ.get("TEST_DATABASE_URL"),
    "TEST_DATABASE_URL is not set",
)
class OxfordPostgreSqlIntegrationTests(unittest.TestCase):
    db_url = os.environ.get("TEST_DATABASE_URL", "")

    def test_repeat_add_and_update_are_incremental(self) -> None:
        suffix = uuid.uuid4().hex
        first_word = f"integration-{suffix}"
        second_word = f"integration-new-{suffix}"
        keys = [
            f"oxford:{first_word}:noun",
            f"oxford:{second_word}:adjective",
        ]

        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            cache_directory = directory / "cache"
            cache_directory.mkdir()
            words_json = directory / "words.json"
            write_json(words_json, [])

            first_entry = {
                "pronunciations": [
                    pronunciation("test", "American English", "https://one.test/a.mp3")
                ],
                "senses": [{"translations": [translation("первый")]}],
            }
            first_path = cache_directory / "first.json"
            write_json(
                first_path,
                cache_wrapper(
                    first_word,
                    [lexical_entry(first_word, "noun", [first_entry])],
                ),
            )

            def current_rows():
                groups, _ = parse_cache_files(cache_directory)
                rows, _ = build_rows(groups, load_definition_index(words_json))
                return rows

            try:
                self.assertEqual(import_rows(current_rows(), self.db_url), 1)
                self.assertEqual(import_rows(current_rows(), self.db_url), 1)

                second_entry = {
                    "pronunciations": [pronunciation("new", "British English")],
                    "senses": [{"translations": [translation("новый")]}],
                }
                write_json(
                    cache_directory / "second.json",
                    cache_wrapper(
                        second_word,
                        [lexical_entry(second_word, "adjective", [second_entry])],
                    ),
                )
                self.assertEqual(import_rows(current_rows(), self.db_url), 2)

                first_entry["senses"][0]["translations"].append(
                    translation("обновлённый")
                )
                write_json(
                    first_path,
                    cache_wrapper(
                        first_word,
                        [lexical_entry(first_word, "noun", [first_entry])],
                    ),
                )
                self.assertEqual(import_rows(current_rows(), self.db_url), 2)

                with sync_connection(self.db_url) as connection:
                    raw = connection.connection.driver_connection
                    assert raw is not None
                    with raw.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT source_lexical_key, translations
                            FROM oxford_lexical_entries
                            WHERE source_lexical_key = ANY(%s)
                            ORDER BY source_lexical_key
                            """,
                            (keys,),
                        )
                        stored = cursor.fetchall()

                self.assertEqual(len(stored), 2)
                first_stored = next(row for row in stored if row[0] == keys[0])
                self.assertEqual(first_stored[1], ["первый", "обновлённый"])
            finally:
                with sync_connection(self.db_url) as connection:
                    raw = connection.connection.driver_connection
                    assert raw is not None
                    with raw.cursor() as cursor:
                        cursor.execute(
                            "DELETE FROM oxford_lexical_entries "
                            "WHERE source_lexical_key = ANY(%s)",
                            (keys,),
                        )


def pronunciation(
    ipa: str,
    dialect: str,
    audio: str = "",
) -> dict:
    value = {
        "dialects": [dialect],
        "phoneticNotation": "IPA",
        "phoneticSpelling": ipa,
    }
    if audio:
        value["audioFile"] = audio
    return value


def translation(text: str, language: str = "ru") -> dict:
    return {"language": language, "text": text}


def cache_wrapper(result_id: str, lexical_entries: list[dict]) -> dict:
    return {
        "query": result_id,
        "resolved": result_id,
        "status": 200,
        "ok": True,
        "data": {
            "results": [
                {
                    "id": result_id,
                    "word": result_id,
                    "lexicalEntries": lexical_entries,
                }
            ]
        },
    }


def lexical_entry(
    word: str,
    category: str,
    entries: list[dict],
) -> dict:
    return {
        "text": word,
        "lexicalCategory": {"id": category, "text": category.title()},
        "entries": entries,
    }


def write_json(path: Path, value) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
