"""Orchestrate OALD audio download runs against PostgreSQL."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection

from scripts.oald.audio.constants import DEFAULT_MAX_AUDIO_BYTES
from scripts.oald.audio.download import download_audio_file, download_with_retries
from scripts.oald.audio.errors import (
    AudioConversionError,
    AudioDownloadError,
    AudioRateLimitError,
    OaldAudioDatabaseError,
)
from scripts.oald.audio.models import (
    AudioCandidate,
    DownloadedAudio,
    DownloadStats,
    VoiceAudio,
)
from scripts.oald.audio.store import (
    load_stored_audio,
    store_failure,
    store_success,
    store_voice_failure,
    store_voice_success,
)
from scripts.oald.audio.transcode import transcode_audio_to_voice
from scripts.oald.oald_preflight import require_oald_schema
from tgbot.db.models import EnglishVariety
from tgbot.db.postgres import async_engine, missing_public_tables
from tgbot.db.tables import (
    bot_telegram_audio_cache,
    oald_audio_files,
    oald_audio_variants,
    oald_entries,
    oald_entry_audio_sources,
)

LOGGER = logging.getLogger("tgbot.oald_audio_download")


async def download_audio_to_postgres(
    db_url: str,
    english_varieties: list[str] | None = None,
    limit: int | None = None,
    force: bool = False,
    request_delay: float = 0.5,
    timeout: float = 30.0,
    retries: int = 3,
    retry_backoff: float = 2.0,
    max_audio_bytes: int = DEFAULT_MAX_AUDIO_BYTES,
    fail_fast: bool = False,
    source_urls: list[str] | None = None,
    fetch_audio: Callable[..., DownloadedAudio] = download_audio_file,
    transcode_voice: Callable[..., VoiceAudio] = transcode_audio_to_voice,
    sleep: Callable[[float], None] = time.sleep,
) -> DownloadStats:
    selected_english_varieties = english_varieties or [
        EnglishVariety.US,
        EnglishVariety.GB,
    ]
    stats = DownloadStats()
    engine = async_engine(db_url, autocommit=True)
    try:
        async with engine.connect() as connection:
            await require_oald_schema(connection)
            clear_telegram_cache = not await missing_public_tables(
                connection,
                [bot_telegram_audio_cache.name],
            )
            candidates = await load_candidates(
                connection,
                english_varieties=selected_english_varieties,
                force=force,
                limit=limit,
                source_urls=source_urls,
            )
        stats.candidates = len(candidates)
        LOGGER.info(
            "Audio candidates=%s english_varieties=%s force=%s",
            f"{stats.candidates:,}",
            ",".join(selected_english_varieties),
            force,
        )

        network_requests = 0
        for position, candidate in enumerate(candidates, start=1):
            needs_download = force or not candidate.has_original
            LOGGER.info(
                "[%s/%s] Preparing %s (%s): %s",
                f"{position:,}",
                f"{stats.candidates:,}",
                candidate.example_word,
                ",".join(candidate.english_varieties),
                candidate.source_url,
            )
            try:
                if needs_download:
                    if network_requests and request_delay:
                        sleep(request_delay)
                    network_requests += 1
                    audio, attempts = download_with_retries(
                        candidate.source_url,
                        timeout=timeout,
                        max_bytes=max_audio_bytes,
                        retries=retries,
                        retry_backoff=retry_backoff,
                        fetch_audio=fetch_audio,
                        sleep=sleep,
                    )
                    async with engine.connect() as connection:
                        await store_success(connection, candidate, audio, attempts)
                    stats.downloaded += 1
                    stats.stored_bytes += len(audio.data)
                    LOGGER.info(
                        "Stored original %s: filename=%s bytes=%s type=%s",
                        candidate.example_word,
                        audio.filename,
                        f"{len(audio.data):,}",
                        audio.content_type,
                    )
                else:
                    async with engine.connect() as connection:
                        audio = await load_stored_audio(connection, candidate)
                    stats.reused_originals += 1
                    LOGGER.info(
                        "Using stored original for %s; no HTTP request",
                        candidate.example_word,
                    )

                try:
                    voice = transcode_voice(
                        audio,
                        timeout=timeout,
                        max_bytes=max_audio_bytes,
                    )
                    async with engine.connect() as connection:
                        await store_voice_success(
                            connection,
                            candidate,
                            audio,
                            voice,
                            clear_telegram_cache=clear_telegram_cache,
                        )
                    stats.voices_prepared += 1
                    stats.voice_bytes += len(voice.data)
                    LOGGER.info(
                        "Stored Telegram voice for %s: filename=%s bytes=%s",
                        candidate.example_word,
                        voice.filename,
                        f"{len(voice.data):,}",
                    )
                except AudioConversionError as exc:
                    async with engine.connect() as connection:
                        await store_voice_failure(connection, candidate, audio, exc)
                    stats.conversion_failed += 1
                    LOGGER.error(
                        "Voice conversion failed for %s (%s): %s",
                        candidate.example_word,
                        ",".join(candidate.english_varieties),
                        exc,
                    )
                    if fail_fast:
                        raise
            except AudioRateLimitError as exc:
                async with engine.connect() as connection:
                    await store_failure(connection, candidate, exc, keep_pending=True)
                stats.rate_limited = True
                LOGGER.error(
                    "OALD rate limit reached for %s. The run stopped "
                    "without waiting; rerun the same command later.",
                    candidate.example_word,
                )
                break
            except AudioDownloadError as exc:
                async with engine.connect() as connection:
                    await store_failure(connection, candidate, exc)
                stats.failed += 1
                LOGGER.error(
                    "Audio download failed for %s (%s): %s",
                    candidate.example_word,
                    ",".join(candidate.english_varieties),
                    exc,
                )
                if fail_fast:
                    raise
        return stats
    except AudioDownloadError, AudioConversionError:
        raise
    except Exception as exc:
        raise OaldAudioDatabaseError(
            "PostgreSQL audio operation failed; verify the database URL and "
            "run `uv run oald-import` first"
        ) from exc
    finally:
        await engine.dispose()


async def load_candidates(
    connection: AsyncConnection,
    english_varieties: list[str],
    force: bool,
    limit: int | None,
    source_urls: list[str] | None = None,
) -> list[AudioCandidate]:
    sql_limit = limit if limit is not None else 2_147_483_647
    needs_work = sa.or_(
        sa.literal(force),
        oald_audio_files.c.audio_data.is_(None),
        oald_audio_variants.c.audio_data.is_(None),
        oald_audio_variants.c.source_sha256 != oald_audio_files.c.sha256,
    )
    url_filter = sa.true()
    if source_urls is not None:
        url_filter = oald_audio_files.c.source_url.in_(source_urls)

    stmt = (
        sa.select(
            oald_audio_files.c.source_url,
            sa.func.min(oald_entries.c.word_us).label("example_word"),
            sa.func.array_agg(
                sa.distinct(oald_entry_audio_sources.c.english_variety)
            ).label("english_varieties"),
            oald_audio_files.c.audio_data.is_not(None).label("has_original"),
        )
        .select_from(
            oald_audio_files.join(
                oald_entry_audio_sources,
                oald_entry_audio_sources.c.source_url == oald_audio_files.c.source_url,
            )
            .join(
                oald_entries,
                oald_entries.c.id == oald_entry_audio_sources.c.entry_id,
            )
            .outerjoin(
                oald_audio_variants,
                oald_audio_variants.c.source_url == oald_audio_files.c.source_url,
            )
        )
        .where(
            oald_entry_audio_sources.c.english_variety.in_(english_varieties),
            needs_work,
            url_filter,
        )
        .group_by(
            oald_audio_files.c.source_url,
            oald_audio_files.c.audio_data.is_not(None),
        )
        .order_by(oald_audio_files.c.source_url)
        .limit(sql_limit)
    )
    rows = (await connection.execute(stmt)).all()
    return [
        AudioCandidate(
            source_url=str(row.source_url),
            example_word=str(row.example_word),
            english_varieties=tuple(row.english_varieties or ()),
            has_original=bool(row.has_original),
        )
        for row in rows
    ]
