"""Write Oxford lexical rows into PostgreSQL."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Iterator

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from scripts.oald.oald_preflight import require_oxford_schema
from scripts.oald.oxford_import.models import OxfordDatabaseError, OxfordRow
from tgbot.db.sync import sync_connection
from tgbot.db.tables import oxford_lexical_entries

LOGGER = logging.getLogger("tgbot.oxford_import")


def import_rows(
    rows: Iterable[OxfordRow],
    db_url: str,
    batch_size: int = 500,
) -> int:
    processed = 0
    try:
        with sync_connection(db_url) as connection:
            require_oxford_schema(connection)
            LOGGER.info("Alembic-managed Oxford cache schema is ready")
            for batch in iter_batches(rows, batch_size):
                values = [row.as_parameters() for row in batch]
                stmt = pg_insert(oxford_lexical_entries).values(values)
                stmt = stmt.on_conflict_do_update(
                    index_elements=[oxford_lexical_entries.c.source_lexical_key],
                    set_={
                        "word_us": stmt.excluded.word_us,
                        "word_gb": stmt.excluded.word_gb,
                        "lexical_category": stmt.excluded.lexical_category,
                        "ipa_us": stmt.excluded.ipa_us,
                        "ipa_gb": stmt.excluded.ipa_gb,
                        "definition": stmt.excluded.definition,
                        "example": stmt.excluded.example,
                        "audio_source_us": stmt.excluded.audio_source_us,
                        "audio_source_gb": stmt.excluded.audio_source_gb,
                        "translations": stmt.excluded.translations,
                    },
                    where=sa.tuple_(
                        oxford_lexical_entries.c.word_us,
                        oxford_lexical_entries.c.word_gb,
                        oxford_lexical_entries.c.lexical_category,
                        oxford_lexical_entries.c.ipa_us,
                        oxford_lexical_entries.c.ipa_gb,
                        oxford_lexical_entries.c.definition,
                        oxford_lexical_entries.c.example,
                        oxford_lexical_entries.c.audio_source_us,
                        oxford_lexical_entries.c.audio_source_gb,
                        oxford_lexical_entries.c.translations,
                    ).is_distinct_from(
                        sa.tuple_(
                            stmt.excluded.word_us,
                            stmt.excluded.word_gb,
                            stmt.excluded.lexical_category,
                            stmt.excluded.ipa_us,
                            stmt.excluded.ipa_gb,
                            stmt.excluded.definition,
                            stmt.excluded.example,
                            stmt.excluded.audio_source_us,
                            stmt.excluded.audio_source_gb,
                            stmt.excluded.translations,
                        )
                    ),
                )
                connection.execute(stmt)
                processed += len(batch)
                LOGGER.info(
                    "Upserted batch of %s rows; processed=%s",
                    f"{len(batch):,}",
                    f"{processed:,}",
                )
    except Exception as exc:
        raise OxfordDatabaseError(
            "PostgreSQL import failed; check the server and connection settings"
        ) from exc
    return processed


def iter_batches(
    rows: Iterable[OxfordRow], batch_size: int
) -> Iterator[list[OxfordRow]]:
    batch: list[OxfordRow] = []
    for row in rows:
        batch.append(row)
        if len(batch) == batch_size:
            yield batch
            batch = []
    if batch:
        yield batch
