"""Admin panel query helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from tgbot.constants import (
    AUDIO_CONVERSION_PREPARED,
    AUDIO_VARIANT_TELEGRAM_VOICE_OPUS,
    CARD_STATUS_DELIVERED,
)
from tgbot.db.mixins.base import PoolBound
from tgbot.db.mixins.cards import CARD_CONTENT_SQL
from tgbot.db.models import VALID_PRONUNCIATIONS, ReservedCard, card_from_row


class AdminMixin(PoolBound):
    async def admin_users_summary(
        self,
        *,
        today_start: datetime,
        week_start: datetime,
        month_start: datetime,
    ) -> dict[str, Any]:
        async with self.pool.connection() as connection:
            totals = await (
                await connection.execute(
                    """
                    SELECT
                        count(*) AS total_users,
                        count(*) FILTER (
                            WHERE is_active AND onboarding_completed
                        ) AS active_users,
                        count(*) FILTER (
                            WHERE paused_at IS NOT NULL
                              AND blocked_at IS NULL
                        ) AS paused_users,
                        count(*) FILTER (
                            WHERE blocked_at IS NOT NULL
                        ) AS blocked_users,
                        count(*) FILTER (WHERE created_at >= %s) AS new_today,
                        count(*) FILTER (WHERE created_at >= %s) AS new_week,
                        count(*) FILTER (WHERE created_at >= %s) AS new_month
                    FROM bot_users
                    """,
                    (today_start, week_start, month_start),
                )
            ).fetchone()
            levels = await (
                await connection.execute(
                    """
                    SELECT level, count(*) AS users
                    FROM bot_users
                    CROSS JOIN LATERAL unnest(selected_levels) AS level
                    WHERE onboarding_completed
                    GROUP BY level
                    ORDER BY level
                    """
                )
            ).fetchall()
            dialects = await (
                await connection.execute(
                    """
                    SELECT pronunciation, count(*) AS users
                    FROM bot_users
                    WHERE onboarding_completed
                    GROUP BY pronunciation
                    ORDER BY pronunciation
                    """
                )
            ).fetchall()
        result = dict(totals)
        result["levels"] = {str(row["level"]): int(row["users"]) for row in levels}
        result["dialects"] = {
            str(row["pronunciation"]): int(row["users"])
            for row in dialects
            if row["pronunciation"]
        }
        return result

    async def admin_user_detail(self, telegram_user_id: int) -> dict[str, Any] | None:
        async with self.pool.connection() as connection:
            row = await (
                await connection.execute(
                    """
                    SELECT users.*,
                           count(cards.id) FILTER (
                               WHERE cards.status = %s
                           ) AS delivered_cards,
                           max(cards.delivered_at) FILTER (
                               WHERE cards.status = %s
                           ) AS last_successful_delivery
                    FROM bot_users AS users
                    LEFT JOIN bot_user_cards AS cards
                      ON cards.telegram_user_id = users.telegram_user_id
                    WHERE users.telegram_user_id = %s
                    GROUP BY users.telegram_user_id
                    """,
                    (
                        CARD_STATUS_DELIVERED,
                        CARD_STATUS_DELIVERED,
                        telegram_user_id,
                    ),
                )
            ).fetchone()
        return dict(row) if row else None

    async def admin_content_summary(self) -> dict[str, int]:
        async with self.pool.connection() as connection:
            row = await (
                await connection.execute(
                    f"""
                    WITH audio AS (
                        SELECT links.entry_id,
                               bool_or(
                                   links.dialect = 'us'
                                   AND variants.conversion_status
                                       = '{AUDIO_CONVERSION_PREPARED}'
                                   AND variants.audio_data IS NOT NULL
                                   AND variants.source_sha256 = files.sha256
                               ) AS has_us_audio,
                               bool_or(
                                   links.dialect = 'gb'
                                   AND variants.conversion_status
                                       = '{AUDIO_CONVERSION_PREPARED}'
                                   AND variants.audio_data IS NOT NULL
                                   AND variants.source_sha256 = files.sha256
                               ) AS has_gb_audio
                        FROM oald_entry_audio_sources AS links
                        JOIN oald_audio_files AS files
                          ON files.source_url = links.source_url
                        LEFT JOIN oald_audio_variants AS variants
                          ON variants.source_url = files.source_url
                         AND variants.variant_type
                             = '{AUDIO_VARIANT_TELEGRAM_VOICE_OPUS}'
                        GROUP BY links.entry_id
                    )
                    SELECT count(*) FILTER (
                        WHERE entries.is_active
                          AND btrim(entries.word_us) <> ''
                          AND btrim(entries.word_gb) <> ''
                          AND btrim(entries.lexical_category) <> ''
                          AND btrim(entries.definition) <> ''
                          AND btrim(entries.example) <> ''
                          AND (
                              btrim(COALESCE(
                                  entries.translations #>> '{{ru,main}}', ''
                              )) <> ''
                              OR CASE
                                  WHEN jsonb_typeof(
                                      entries.translations #> '{{ru,also}}'
                                  ) = 'array'
                                  THEN jsonb_array_length(
                                      entries.translations #> '{{ru,also}}'
                                  ) > 0
                                  ELSE FALSE
                              END
                          )
                          AND (
                              (
                                  cardinality(entries.ipa_us) > 0
                                  AND COALESCE(audio.has_us_audio, FALSE)
                              )
                              OR (
                                  cardinality(entries.ipa_gb) > 0
                                  AND COALESCE(audio.has_gb_audio, FALSE)
                              )
                          )
                    ) AS ready_entries
                    FROM oald_entries AS entries
                    LEFT JOIN audio ON audio.entry_id = entries.id
                    """
                )
            ).fetchone()
        return {"ready_entries": int(row["ready_entries"])}

    async def admin_word_search(
        self,
        word: str,
        *,
        limit: int = 10,
    ) -> tuple[dict[str, Any], ...]:
        async with self.pool.connection() as connection:
            rows = await (
                await connection.execute(
                    """
                    SELECT entries.id, entries.word_us, entries.word_gb,
                           entries.lexical_category, entries.cefr
                    FROM oald_entries AS entries
                    WHERE lower(entries.word_us) = lower(%s)
                       OR lower(entries.word_gb) = lower(%s)
                    ORDER BY entries.lexical_category, entries.id
                    LIMIT %s
                    """,
                    (word, word, limit),
                )
            ).fetchall()
        return tuple(dict(row) for row in rows)

    async def admin_preview_card(
        self,
        *,
        entry_id: int | None = None,
        dialect: str | None = None,
        random_card: bool = False,
    ) -> ReservedCard | None:
        where = (
            "WHERE entries.id = %s"
            if entry_id is not None
            else (
                "WHERE entries.is_active AND ("
                "us_audio.source_url IS NOT NULL OR gb_audio.source_url IS NOT NULL)"
            )
        )
        order = "ORDER BY random()" if random_card else "ORDER BY entries.id"
        query = f"{CARD_CONTENT_SQL} {where} {order} LIMIT 1"
        parameters: tuple[Any, ...] = (entry_id,) if entry_id is not None else ()
        async with self.pool.connection() as connection:
            row = await (await connection.execute(query, parameters)).fetchone()
        if not row:
            return None
        available_us = row["us_source_url"] is not None
        available_gb = row["gb_source_url"] is not None
        requested = (dialect or "").lower()
        if requested == "both" and not (available_us and available_gb):
            return None
        if requested == "us" and not available_us:
            return None
        if requested == "gb" and not available_gb:
            return None
        selected = requested or (
            "both" if available_us and available_gb else "us" if available_us else "gb"
        )
        if selected not in VALID_PRONUNCIATIONS:
            return None
        return card_from_row(row, dialect=selected, history_id=0)
