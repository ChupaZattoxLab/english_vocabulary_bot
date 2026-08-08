"""Card reservation, delivery history, and Telegram audio-file cache."""

from __future__ import annotations

from datetime import datetime

from tgbot.constants import (
    AUDIO_CONVERSION_PREPARED,
    AUDIO_VARIANT_TELEGRAM_VOICE_OPUS,
    CARD_ACTIVE_STATUSES,
    CARD_RESERVATION_TIMEOUT_MINUTES,
    CARD_STATUS_DELIVERED,
    CARD_STATUS_FAILED,
    CARD_STATUS_RESERVED,
    ERROR_MESSAGE_MAX_LEN,
    ERROR_TYPE_MAX_LEN,
    ERROR_TYPE_STALE_RESERVATION,
)
from tgbot.db.mixins.base import PoolBound
from tgbot.db.models import VALID_PRONUNCIATIONS, ReservedCard, card_from_row

_ACTIVE_STATUSES_SQL = ", ".join(f"'{status}'" for status in CARD_ACTIVE_STATUSES)

CARD_CONTENT_SQL = f"""
SELECT
    entries.id AS entry_id,
    entries.word_us,
    entries.word_gb,
    entries.lexical_category,
    entries.cefr,
    entries.definition,
    entries.example,
    entries.ipa_us,
    entries.ipa_gb,
    entries.translations,
    us_audio.source_url AS us_source_url,
    us_audio.source_position AS us_source_position,
    us_audio.audio_data AS us_audio_data,
    us_audio.content_type AS us_content_type,
    us_audio.filename AS us_filename,
    gb_audio.source_url AS gb_source_url,
    gb_audio.source_position AS gb_source_position,
    gb_audio.audio_data AS gb_audio_data,
    gb_audio.content_type AS gb_content_type,
    gb_audio.filename AS gb_filename
FROM oald_entries AS entries
LEFT JOIN LATERAL (
    SELECT links.source_url,
           links.source_position,
           voice.audio_data,
           voice.content_type,
           voice.filename
    FROM oald_entry_audio_sources AS links
    JOIN oald_audio_files AS files
      ON files.source_url = links.source_url
    JOIN oald_audio_variants AS voice
      ON voice.source_url = files.source_url
     AND voice.variant_type = '{AUDIO_VARIANT_TELEGRAM_VOICE_OPUS}'
     AND voice.conversion_status = '{AUDIO_CONVERSION_PREPARED}'
     AND voice.source_sha256 = files.sha256
    WHERE links.entry_id = entries.id
      AND links.dialect = 'us'
      AND voice.audio_data IS NOT NULL
    ORDER BY links.source_position
    LIMIT 1
) AS us_audio ON TRUE
LEFT JOIN LATERAL (
    SELECT links.source_url,
           links.source_position,
           voice.audio_data,
           voice.content_type,
           voice.filename
    FROM oald_entry_audio_sources AS links
    JOIN oald_audio_files AS files
      ON files.source_url = links.source_url
    JOIN oald_audio_variants AS voice
      ON voice.source_url = files.source_url
     AND voice.variant_type = '{AUDIO_VARIANT_TELEGRAM_VOICE_OPUS}'
     AND voice.conversion_status = '{AUDIO_CONVERSION_PREPARED}'
     AND voice.source_sha256 = files.sha256
    WHERE links.entry_id = entries.id
      AND links.dialect = 'gb'
      AND voice.audio_data IS NOT NULL
    ORDER BY links.source_position
    LIMIT 1
) AS gb_audio ON TRUE
"""


class CardsMixin(PoolBound):
    async def reserve_card(
        self,
        telegram_user_id: int,
        scheduled_slot: datetime,
        *,
        require_active: bool = True,
    ) -> ReservedCard | None:
        async with self.pool.connection() as connection:
            async with connection.transaction():
                await connection.execute(
                    "SELECT pg_advisory_xact_lock(%s)",
                    (telegram_user_id,),
                )
                await connection.execute(
                    f"""
                    UPDATE bot_user_cards
                    SET status = '{CARD_STATUS_FAILED}',
                        error_type = '{ERROR_TYPE_STALE_RESERVATION}',
                        error_message = 'reservation timed out before delivery finished'
                    WHERE telegram_user_id = %s
                      AND status = '{CARD_STATUS_RESERVED}'
                      AND created_at < CURRENT_TIMESTAMP
                          - make_interval(mins => {CARD_RESERVATION_TIMEOUT_MINUTES})
                    """,
                    (telegram_user_id,),
                )
                user = await (
                    await connection.execute(
                        """
                        SELECT selected_levels, pronunciation, is_active,
                               onboarding_completed
                        FROM bot_users
                        WHERE telegram_user_id = %s
                        """,
                        (telegram_user_id,),
                    )
                ).fetchone()
                if (
                    not user
                    or not user["onboarding_completed"]
                    or not user["selected_levels"]
                    or user["pronunciation"] not in VALID_PRONUNCIATIONS
                    or (require_active and not user["is_active"])
                ):
                    return None

                existing = await (
                    await connection.execute(
                        f"""
                        SELECT status
                        FROM bot_user_cards
                        WHERE telegram_user_id = %s
                          AND scheduled_slot = %s
                          AND status IN ({_ACTIVE_STATUSES_SQL})
                        """,
                        (telegram_user_id, scheduled_slot),
                    )
                ).fetchone()
                if existing:
                    return None

                dialect = str(user["pronunciation"])
                query = f"""
                    {CARD_CONTENT_SQL}
                    WHERE entries.is_active
                      AND entries.cefr = ANY(%s)
                      AND CASE %s
                          WHEN 'us' THEN us_audio.source_url IS NOT NULL
                          WHEN 'gb' THEN gb_audio.source_url IS NOT NULL
                          WHEN 'both' THEN
                              us_audio.source_url IS NOT NULL
                              AND gb_audio.source_url IS NOT NULL
                          ELSE FALSE
                      END
                      AND NOT EXISTS (
                          SELECT 1
                          FROM bot_user_cards AS history
                          WHERE history.telegram_user_id = %s
                            AND history.entry_id = entries.id
                            AND history.status IN ({_ACTIVE_STATUSES_SQL})
                      )
                    ORDER BY random()
                    LIMIT 1
                    """
                row = await (
                    await connection.execute(
                        query,
                        (
                            list(user["selected_levels"]),
                            dialect,
                            telegram_user_id,
                        ),
                    )
                ).fetchone()
                if not row:
                    return None

                history = await (
                    await connection.execute(
                        """
                        INSERT INTO bot_user_cards (
                            telegram_user_id,
                            entry_id,
                            dialect,
                            source_url,
                            source_url_gb,
                            scheduled_slot
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            telegram_user_id,
                            row["entry_id"],
                            dialect,
                            row[
                                "gb_source_url" if dialect == "gb" else "us_source_url"
                            ],
                            row["gb_source_url"] if dialect == "both" else None,
                            scheduled_slot,
                        ),
                    )
                ).fetchone()

        return card_from_row(
            row,
            dialect=dialect,
            history_id=int(history["id"]),
        )

    async def finish_delivery(
        self,
        history_id: int,
        *,
        delivered: bool,
        telegram_message_id: int | None = None,
        error_type: str = "",
        error_message: str = "",
    ) -> None:
        async with self.pool.connection() as connection:
            async with connection.transaction():
                row = await (
                    await connection.execute(
                        """
                        UPDATE bot_user_cards
                        SET status = %s,
                            telegram_message_id = %s,
                            error_type = %s,
                            error_message = %s,
                            delivered_at = CASE
                                WHEN %s THEN CURRENT_TIMESTAMP
                                ELSE NULL
                            END
                        WHERE id = %s
                        RETURNING telegram_user_id
                        """,
                        (
                            CARD_STATUS_DELIVERED if delivered else CARD_STATUS_FAILED,
                            telegram_message_id,
                            "" if delivered else error_type[:ERROR_TYPE_MAX_LEN],
                            error_message[:ERROR_MESSAGE_MAX_LEN],
                            delivered,
                            history_id,
                        ),
                    )
                ).fetchone()
                if delivered and row:
                    await connection.execute(
                        """
                        UPDATE bot_users
                        SET last_delivery_at = CURRENT_TIMESTAMP,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE telegram_user_id = %s
                        """,
                        (row["telegram_user_id"],),
                    )

    async def cached_audio_file_id(
        self,
        source_url: str,
        send_method: str,
    ) -> str | None:
        async with self.pool.connection() as connection:
            row = await (
                await connection.execute(
                    """
                    SELECT telegram_file_id
                    FROM bot_telegram_audio_cache
                    WHERE source_url = %s AND send_method = %s
                    """,
                    (source_url, send_method),
                )
            ).fetchone()
        return str(row["telegram_file_id"]) if row else None

    async def cache_audio_file_id(
        self,
        source_url: str,
        send_method: str,
        telegram_file_id: str,
    ) -> None:
        async with self.pool.connection() as connection:
            await connection.execute(
                """
                INSERT INTO bot_telegram_audio_cache (
                    source_url, send_method, telegram_file_id
                ) VALUES (%s, %s, %s)
                ON CONFLICT (source_url, send_method) DO UPDATE SET
                    telegram_file_id = EXCLUDED.telegram_file_id,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (source_url, send_method, telegram_file_id),
            )

    async def clear_cached_audio_file_id(
        self,
        source_url: str,
        send_method: str,
    ) -> None:
        async with self.pool.connection() as connection:
            await connection.execute(
                """
                DELETE FROM bot_telegram_audio_cache
                WHERE source_url = %s AND send_method = %s
                """,
                (source_url, send_method),
            )
