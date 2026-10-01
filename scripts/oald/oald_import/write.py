"""Write OALD entries into PostgreSQL."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from scripts.oald.oald_import.models import ImportResult, OaldDatabaseError, OaldEntry
from scripts.oald.oald_preflight import require_oald_schema
from tgbot.db.sync import sync_connection
from tgbot.db.tables import (
    oald_audio_files,
    oald_entries,
    oald_entry_audio_sources,
)

LOGGER = logging.getLogger("tgbot.oald_import")


def import_entries(
    entries: Iterable[OaldEntry],
    db_url: str,
    batch_size: int = 500,
) -> ImportResult:
    try:
        entry_count = 0
        audio_reference_count = 0
        unique_audio_urls: set[str] = set()
        with sync_connection(db_url) as connection:
            require_oald_schema(connection)
            LOGGER.info("Alembic-managed OALD schema is ready")
            for batch in iter_batches(entries, batch_size):
                imported_ids: list[int] = []
                links: list[dict[str, Any]] = []
                batch_urls: set[str] = set()

                for entry in batch:
                    stmt = pg_insert(oald_entries).values(**entry.values())
                    stmt = stmt.on_conflict_do_update(
                        index_elements=[oald_entries.c.definition_url_oxford],
                        set_={
                            "word_us": stmt.excluded.word_us,
                            "word_gb": stmt.excluded.word_gb,
                            "lexical_category": stmt.excluded.lexical_category,
                            "cefr": stmt.excluded.cefr,
                            "definition_url_cambridge": (
                                stmt.excluded.definition_url_cambridge
                            ),
                            "ipa_us": stmt.excluded.ipa_us,
                            "ipa_gb": stmt.excluded.ipa_gb,
                            "definition": stmt.excluded.definition,
                            "example": stmt.excluded.example,
                            "audio_source_us": stmt.excluded.audio_source_us,
                            "audio_source_gb": stmt.excluded.audio_source_gb,
                            "translations": stmt.excluded.translations,
                            "updated_at": sa.func.current_timestamp(),
                        },
                    ).returning(oald_entries.c.id)
                    entry_id = connection.execute(stmt).scalar_one()
                    imported_ids.append(int(entry_id))
                    for dialect, position, source_url in entry.audio_references():
                        links.append(
                            {
                                "entry_id": entry_id,
                                "dialect": dialect,
                                "source_position": position,
                                "source_url": source_url,
                            }
                        )
                        batch_urls.add(source_url)

                if imported_ids:
                    connection.execute(
                        sa.delete(oald_entry_audio_sources).where(
                            oald_entry_audio_sources.c.entry_id.in_(imported_ids)
                        )
                    )
                if batch_urls:
                    connection.execute(
                        pg_insert(oald_audio_files)
                        .values(
                            [
                                {"source_url": source_url}
                                for source_url in sorted(batch_urls)
                            ]
                        )
                        .on_conflict_do_nothing(
                            index_elements=[oald_audio_files.c.source_url]
                        )
                    )
                if links:
                    connection.execute(sa.insert(oald_entry_audio_sources), links)

                entry_count += len(batch)
                audio_reference_count += len(links)
                unique_audio_urls.update(batch_urls)
                LOGGER.info(
                    "Imported batch=%s; entries=%s; audio references=%s",
                    f"{len(batch):,}",
                    f"{entry_count:,}",
                    f"{audio_reference_count:,}",
                )

        return ImportResult(
            entries=entry_count,
            audio_references=audio_reference_count,
            unique_audio_urls=len(unique_audio_urls),
        )
    except OaldDatabaseError:
        raise
    except Exception as exc:
        raise OaldDatabaseError(
            "PostgreSQL OALD import failed; the transaction was rolled back"
        ) from exc


def iter_batches(
    entries: Iterable[OaldEntry],
    batch_size: int,
) -> Iterator[list[OaldEntry]]:
    batch: list[OaldEntry] = []
    for entry in entries:
        batch.append(entry)
        if len(batch) >= batch_size:
            yield batch
            batch = []
    if batch:
        yield batch
