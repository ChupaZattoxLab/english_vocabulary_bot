"""Persist downloaded originals and Telegram voice variants."""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection

from scripts.oald.audio.errors import (
    AudioConversionError,
    AudioDownloadError,
    OaldAudioDatabaseError,
)
from scripts.oald.audio.models import AudioCandidate, DownloadedAudio, VoiceAudio
from tgbot.db.models import (
    AudioConversionStatus,
    AudioDownloadStatus,
    AudioVariantType,
    TelegramSendMethod,
)
from tgbot.db.tables import (
    bot_telegram_audio_cache,
    oald_audio_files,
    oald_audio_variants,
)


def store_success(
    connection: Connection,
    candidate: AudioCandidate,
    audio: DownloadedAudio,
    attempts: int,
) -> None:
    connection.execute(
        sa.update(oald_audio_files)
        .where(oald_audio_files.c.source_url == candidate.source_url)
        .values(
            audio_data=audio.data,
            content_type=audio.content_type,
            filename=audio.filename,
            size_bytes=len(audio.data),
            sha256=audio.sha256,
            download_status=AudioDownloadStatus.DOWNLOADED,
            last_http_status=audio.http_status,
            last_error="",
            attempt_count=oald_audio_files.c.attempt_count + attempts,
            last_attempted_at=sa.func.current_timestamp(),
            downloaded_at=sa.func.current_timestamp(),
            updated_at=sa.func.current_timestamp(),
        )
    )


def store_failure(
    connection: Connection,
    candidate: AudioCandidate,
    error: AudioDownloadError,
    keep_pending: bool = False,
) -> None:
    pending_or_failed = (
        AudioDownloadStatus.PENDING if keep_pending else AudioDownloadStatus.FAILED
    )
    connection.execute(
        sa.update(oald_audio_files)
        .where(oald_audio_files.c.source_url == candidate.source_url)
        .values(
            download_status=sa.case(
                (oald_audio_files.c.audio_data.is_(None), pending_or_failed),
                else_=AudioDownloadStatus.DOWNLOADED,
            ),
            last_http_status=error.status_code,
            last_error=str(error)[:2000],
            attempt_count=oald_audio_files.c.attempt_count + error.attempts,
            last_attempted_at=sa.func.current_timestamp(),
            updated_at=sa.func.current_timestamp(),
        )
    )


def store_voice_success(
    connection: Connection,
    candidate: AudioCandidate,
    original: DownloadedAudio,
    voice: VoiceAudio,
    clear_telegram_cache: bool = False,
) -> None:
    stmt = pg_insert(oald_audio_variants).values(
        source_url=candidate.source_url,
        variant_type=AudioVariantType.TELEGRAM_VOICE_OPUS,
        source_sha256=original.sha256,
        audio_data=voice.data,
        content_type="audio/ogg",
        filename=voice.filename,
        size_bytes=len(voice.data),
        sha256=voice.sha256,
        conversion_status=AudioConversionStatus.PREPARED,
        last_error="",
        attempt_count=1,
        converted_at=sa.func.current_timestamp(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            oald_audio_variants.c.source_url,
            oald_audio_variants.c.variant_type,
        ],
        set_={
            "source_sha256": stmt.excluded.source_sha256,
            "audio_data": stmt.excluded.audio_data,
            "content_type": stmt.excluded.content_type,
            "filename": stmt.excluded.filename,
            "size_bytes": stmt.excluded.size_bytes,
            "sha256": stmt.excluded.sha256,
            "conversion_status": AudioConversionStatus.PREPARED,
            "last_error": "",
            "attempt_count": oald_audio_variants.c.attempt_count + 1,
            "converted_at": sa.func.current_timestamp(),
            "updated_at": sa.func.current_timestamp(),
        },
    )
    connection.execute(stmt)
    if clear_telegram_cache:
        connection.execute(
            sa.delete(bot_telegram_audio_cache).where(
                bot_telegram_audio_cache.c.source_url == candidate.source_url,
                bot_telegram_audio_cache.c.send_method == TelegramSendMethod.VOICE,
            )
        )


def store_voice_failure(
    connection: Connection,
    candidate: AudioCandidate,
    original: DownloadedAudio,
    error: AudioConversionError,
) -> None:
    stmt = pg_insert(oald_audio_variants).values(
        source_url=candidate.source_url,
        variant_type=AudioVariantType.TELEGRAM_VOICE_OPUS,
        source_sha256=original.sha256,
        conversion_status=AudioConversionStatus.FAILED,
        last_error=str(error)[:2000],
        attempt_count=1,
    )
    same_sha = oald_audio_variants.c.source_sha256 == stmt.excluded.source_sha256
    stmt = stmt.on_conflict_do_update(
        index_elements=[
            oald_audio_variants.c.source_url,
            oald_audio_variants.c.variant_type,
        ],
        set_={
            "source_sha256": sa.case(
                (same_sha, oald_audio_variants.c.source_sha256),
                else_=stmt.excluded.source_sha256,
            ),
            "audio_data": sa.case(
                (same_sha, oald_audio_variants.c.audio_data),
                else_=None,
            ),
            "content_type": sa.case(
                (same_sha, oald_audio_variants.c.content_type),
                else_="",
            ),
            "filename": sa.case(
                (same_sha, oald_audio_variants.c.filename),
                else_="",
            ),
            "size_bytes": sa.case(
                (same_sha, oald_audio_variants.c.size_bytes),
                else_=None,
            ),
            "sha256": sa.case(
                (same_sha, oald_audio_variants.c.sha256),
                else_="",
            ),
            "conversion_status": sa.case(
                (
                    sa.and_(same_sha, oald_audio_variants.c.audio_data.is_not(None)),
                    AudioConversionStatus.PREPARED,
                ),
                else_=AudioConversionStatus.FAILED,
            ),
            "last_error": stmt.excluded.last_error,
            "attempt_count": oald_audio_variants.c.attempt_count + 1,
            "converted_at": sa.case(
                (same_sha, oald_audio_variants.c.converted_at),
                else_=None,
            ),
            "updated_at": sa.func.current_timestamp(),
        },
    )
    connection.execute(stmt)


def load_stored_audio(
    connection: Connection,
    candidate: AudioCandidate,
) -> DownloadedAudio:
    row = connection.execute(
        sa.select(
            oald_audio_files.c.audio_data,
            oald_audio_files.c.content_type,
            oald_audio_files.c.filename,
            oald_audio_files.c.sha256,
            oald_audio_files.c.last_http_status,
        ).where(
            oald_audio_files.c.source_url == candidate.source_url,
            oald_audio_files.c.audio_data.is_not(None),
        )
    ).first()
    if row is None:
        raise OaldAudioDatabaseError(
            f"stored audio disappeared for {candidate.source_url}"
        )
    return DownloadedAudio(
        data=bytes(row.audio_data),
        content_type=str(row.content_type),
        filename=str(row.filename),
        sha256=str(row.sha256).strip(),
        http_status=int(row.last_http_status)
        if row.last_http_status is not None
        else None,
    )
