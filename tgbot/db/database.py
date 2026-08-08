"""Async PostgreSQL access for users, delivery history, and OALD cards."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

from alembic.config import Config as AlembicConfig
from alembic.script import ScriptDirectory
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from tgbot.config import PROJECT_ROOT

VALID_LEVELS = ("a1", "a2", "b1", "b2", "c1", "c2")
REQUIRED_TABLES = (
    "oald_entries",
    "oald_audio_files",
    "oald_entry_audio_sources",
    "oald_audio_variants",
    "bot_users",
    "bot_user_cards",
    "bot_scheduler_runs",
    "bot_telegram_audio_cache",
)


@lru_cache(maxsize=1)
def migration_head() -> str:
    config = AlembicConfig(str(PROJECT_ROOT / "alembic.ini"))
    return ScriptDirectory.from_config(config).get_current_head()


CARD_CONTENT_SQL = """
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
     AND voice.variant_type = 'telegram_voice_opus'
     AND voice.conversion_status = 'prepared'
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
     AND voice.variant_type = 'telegram_voice_opus'
     AND voice.conversion_status = 'prepared'
     AND voice.source_sha256 = files.sha256
    WHERE links.entry_id = entries.id
      AND links.dialect = 'gb'
      AND voice.audio_data IS NOT NULL
    ORDER BY links.source_position
    LIMIT 1
) AS gb_audio ON TRUE
"""


class DatabaseError(RuntimeError):
    """Raised when the bot database cannot be initialized safely."""


@dataclass(frozen=True)
class BotUser:
    telegram_user_id: int
    chat_id: int
    username: str
    first_name: str
    selected_levels: tuple[str, ...]
    pronunciation: str | None
    onboarding_completed: bool
    is_active: bool


@dataclass(frozen=True)
class ActiveUser:
    telegram_user_id: int
    chat_id: int


@dataclass(frozen=True)
class ReservedAudio:
    dialect: str
    source_url: str
    audio_data: bytes
    content_type: str
    filename: str


@dataclass(frozen=True)
class ReservedCard:
    history_id: int
    entry_id: int
    word: str
    lexical_category: str
    cefr: str
    definition: str
    example: str
    ipa: str
    dialect: str
    translation: str
    source_url: str
    audio_data: bytes
    content_type: str
    filename: str
    word_us: str = ""
    word_gb: str = ""
    ipa_us: str = ""
    ipa_gb: str = ""
    secondary_audio: ReservedAudio | None = None


def _pool_kwargs(database_url: str) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "row_factory": dict_row,
        "connect_timeout": 10,
    }
    if urlparse(database_url).hostname == "localhost":
        kwargs["hostaddr"] = "127.0.0.1"
    return kwargs


def _user_from_row(row: dict[str, Any]) -> BotUser:
    return BotUser(
        telegram_user_id=int(row["telegram_user_id"]),
        chat_id=int(row["chat_id"]),
        username=str(row["username"]),
        first_name=str(row["first_name"]),
        selected_levels=tuple(row["selected_levels"]),
        pronunciation=row["pronunciation"],
        onboarding_completed=bool(row["onboarding_completed"]),
        is_active=bool(row["is_active"]),
    )


def _selected_ipa(values: list[str], position: int | None) -> str:
    if not values:
        return ""
    if position is not None and 0 <= position < len(values):
        return str(values[position])
    return str(values[0])


def _translation_text(translations: dict[str, Any] | None) -> str:
    russian = (translations or {}).get("ru") or {}
    values = [str(russian.get("main") or "").strip()]
    values.extend(str(value).strip() for value in russian.get("also") or [])
    return ", ".join(value for value in dict.fromkeys(values) if value)


def _card_from_row(
    row: dict[str, Any],
    *,
    dialect: str,
    history_id: int,
) -> ReservedCard:
    normalized = dialect.lower()
    ipa_us = _selected_ipa(row["ipa_us"], row["us_source_position"])
    ipa_gb = _selected_ipa(row["ipa_gb"], row["gb_source_position"])
    primary_prefix = "gb" if normalized == "gb" else "us"
    return ReservedCard(
        history_id=history_id,
        entry_id=int(row["entry_id"]),
        word=str(row[f"word_{primary_prefix}"]),
        lexical_category=str(row["lexical_category"]),
        cefr=str(row["cefr"]).upper(),
        definition=str(row["definition"]),
        example=str(row["example"]),
        ipa=ipa_gb if normalized == "gb" else ipa_us,
        dialect=normalized.upper(),
        translation=_translation_text(row["translations"]),
        source_url=str(row[f"{primary_prefix}_source_url"]),
        audio_data=bytes(row[f"{primary_prefix}_audio_data"]),
        content_type=str(row[f"{primary_prefix}_content_type"]),
        filename=str(row[f"{primary_prefix}_filename"]),
        word_us=str(row["word_us"]),
        word_gb=str(row["word_gb"]),
        ipa_us=ipa_us,
        ipa_gb=ipa_gb,
        secondary_audio=(
            ReservedAudio(
                dialect="GB",
                source_url=str(row["gb_source_url"]),
                audio_data=bytes(row["gb_audio_data"]),
                content_type=str(row["gb_content_type"]),
                filename=str(row["gb_filename"]),
            )
            if normalized == "both"
            else None
        ),
    )


class Database:
    def __init__(self, database_url: str, *, pool_size: int = 5):
        self.pool = AsyncConnectionPool(
            conninfo=database_url,
            kwargs=_pool_kwargs(database_url),
            min_size=1,
            max_size=pool_size,
            open=False,
            name="tgbot",
        )

    async def open(self) -> None:
        await self.pool.open(wait=True, timeout=30)
        try:
            await self.verify_schema()
        except Exception:
            await self.pool.close()
            raise

    async def close(self) -> None:
        await self.pool.close()

    async def verify_schema(self) -> None:
        async with self.pool.connection() as connection:
            rows = await (
                await connection.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name = ANY(%s)
                    """,
                    (list(REQUIRED_TABLES),),
                )
            ).fetchall()
            existing = {str(row["table_name"]) for row in rows}
            missing = set(REQUIRED_TABLES) - existing
            if missing:
                raise DatabaseError(
                    "Database schema is incomplete; missing tables: "
                    f"{', '.join(sorted(missing))}. Run "
                    "`uv run migrate`."
                )

            version_table = await (
                await connection.execute(
                    "SELECT to_regclass('public.alembic_version') AS name"
                )
            ).fetchone()
            if not version_table or version_table["name"] is None:
                raise DatabaseError(
                    "Database is not managed by Alembic. Run `uv run migrate`."
                )
            version = await (
                await connection.execute("SELECT version_num FROM alembic_version")
            ).fetchone()
            expected = migration_head()
            current = str(version["version_num"]) if version else "<none>"
            if current != expected:
                raise DatabaseError(
                    f"Database migration is {current}, expected {expected}. "
                    "Run `uv run migrate`."
                )

    async def upsert_user(
        self,
        *,
        telegram_user_id: int,
        chat_id: int,
        username: str,
        first_name: str,
    ) -> BotUser:
        async with self.pool.connection() as connection:
            row = await (
                await connection.execute(
                    """
                    INSERT INTO bot_users (
                        telegram_user_id, chat_id, username, first_name
                    ) VALUES (%s, %s, %s, %s)
                    ON CONFLICT (telegram_user_id) DO UPDATE SET
                        chat_id = EXCLUDED.chat_id,
                        username = EXCLUDED.username,
                        first_name = EXCLUDED.first_name,
                        blocked_at = NULL,
                        is_active = CASE
                            WHEN bot_users.paused_at IS NULL
                                 AND bot_users.onboarding_completed
                                THEN TRUE
                            ELSE bot_users.is_active
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    RETURNING *
                    """,
                    (telegram_user_id, chat_id, username, first_name),
                )
            ).fetchone()
        return _user_from_row(row)

    async def get_user(self, telegram_user_id: int) -> BotUser | None:
        async with self.pool.connection() as connection:
            row = await (
                await connection.execute(
                    "SELECT * FROM bot_users WHERE telegram_user_id = %s",
                    (telegram_user_id,),
                )
            ).fetchone()
        return _user_from_row(row) if row else None

    async def toggle_level(self, telegram_user_id: int, level: str) -> BotUser:
        normalized = level.lower()
        if normalized not in VALID_LEVELS:
            raise ValueError(f"unsupported CEFR level {level!r}")
        async with self.pool.connection() as connection:
            row = await (
                await connection.execute(
                    """
                    UPDATE bot_users
                    SET selected_levels = CASE
                            WHEN %s = ANY(selected_levels)
                                THEN array_remove(selected_levels, %s)
                            ELSE array_append(selected_levels, %s)
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE telegram_user_id = %s
                    RETURNING *
                    """,
                    (normalized, normalized, normalized, telegram_user_id),
                )
            ).fetchone()
        if not row:
            raise DatabaseError("bot user does not exist")
        return _user_from_row(row)

    async def set_pronunciation(
        self,
        telegram_user_id: int,
        dialect: str,
    ) -> BotUser:
        normalized = dialect.lower()
        if normalized not in {"us", "gb", "both"}:
            raise ValueError(f"unsupported pronunciation {dialect!r}")
        async with self.pool.connection() as connection:
            row = await (
                await connection.execute(
                    """
                    UPDATE bot_users
                    SET pronunciation = %s,
                        onboarding_completed = cardinality(selected_levels) > 0,
                        is_active = CASE
                            WHEN paused_at IS NOT NULL OR blocked_at IS NOT NULL
                                THEN FALSE
                            ELSE cardinality(selected_levels) > 0
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE telegram_user_id = %s
                    RETURNING *
                    """,
                    (normalized, telegram_user_id),
                )
            ).fetchone()
        if not row:
            raise DatabaseError("bot user does not exist")
        return _user_from_row(row)

    async def clear_blocked_marker(self, telegram_user_id: int) -> None:
        """Clear blocked_at after the user messages again; do not resume schedule."""
        async with self.pool.connection() as connection:
            await connection.execute(
                """
                UPDATE bot_users
                SET blocked_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = %s
                  AND blocked_at IS NOT NULL
                """,
                (telegram_user_id,),
            )

    async def set_active(self, telegram_user_id: int, active: bool) -> bool:
        async with self.pool.connection() as connection:
            result = await connection.execute(
                """
                UPDATE bot_users
                SET is_active = %s,
                    paused_at = CASE
                        WHEN %s THEN NULL
                        ELSE CURRENT_TIMESTAMP
                    END,
                    blocked_at = CASE WHEN %s THEN NULL ELSE blocked_at END,
                    updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = %s
                  AND onboarding_completed
                """,
                (active, active, active, telegram_user_id),
            )
        return result.rowcount > 0

    async def active_users(self) -> list[ActiveUser]:
        async with self.pool.connection() as connection:
            rows = await (
                await connection.execute(
                    """
                    SELECT telegram_user_id, chat_id
                    FROM bot_users
                    WHERE is_active
                      AND onboarding_completed
                      AND cardinality(selected_levels) > 0
                      AND pronunciation IS NOT NULL
                    ORDER BY telegram_user_id
                    """
                )
            ).fetchall()
        return [
            ActiveUser(
                telegram_user_id=int(row["telegram_user_id"]),
                chat_id=int(row["chat_id"]),
            )
            for row in rows
        ]

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
                    """
                    UPDATE bot_user_cards
                    SET status = 'failed',
                        error_type = 'stale_reservation',
                        error_message = 'reservation timed out before delivery finished'
                    WHERE telegram_user_id = %s
                      AND status = 'reserved'
                      AND created_at < CURRENT_TIMESTAMP - INTERVAL '15 minutes'
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
                    or user["pronunciation"] not in {"us", "gb", "both"}
                    or (require_active and not user["is_active"])
                ):
                    return None

                existing = await (
                    await connection.execute(
                        """
                        SELECT status
                        FROM bot_user_cards
                        WHERE telegram_user_id = %s
                          AND scheduled_slot = %s
                          AND status IN ('delivered', 'reserved')
                        """,
                        (telegram_user_id, scheduled_slot),
                    )
                ).fetchone()
                if existing:
                    return None

                dialect = str(user["pronunciation"])
                row = await (
                    await connection.execute(
                        """
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
                             AND voice.variant_type = 'telegram_voice_opus'
                             AND voice.conversion_status = 'prepared'
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
                             AND voice.variant_type = 'telegram_voice_opus'
                             AND voice.conversion_status = 'prepared'
                             AND voice.source_sha256 = files.sha256
                            WHERE links.entry_id = entries.id
                              AND links.dialect = 'gb'
                              AND voice.audio_data IS NOT NULL
                            ORDER BY links.source_position
                            LIMIT 1
                        ) AS gb_audio ON TRUE
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
                                AND history.status IN ('delivered', 'reserved')
                          )
                        ORDER BY random()
                        LIMIT 1
                        """,
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

        return _card_from_row(
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
                            "delivered" if delivered else "failed",
                            telegram_message_id,
                            "" if delivered else error_type[:100],
                            error_message[:2000],
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

    async def deactivate_user(self, telegram_user_id: int) -> None:
        async with self.pool.connection() as connection:
            await connection.execute(
                """
                UPDATE bot_users
                SET is_active = FALSE,
                    blocked_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE telegram_user_id = %s
                """,
                (telegram_user_id,),
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

    async def claim_scheduler_run(
        self,
        scheduled_slot: datetime,
        *,
        grace_minutes: int = 60,
    ) -> bool:
        """Claim a slot, or reclaim it for retries within the grace window."""
        async with self.pool.connection() as connection:
            row = await (
                await connection.execute(
                    """
                    INSERT INTO bot_scheduler_runs (scheduled_slot)
                    VALUES (%s)
                    ON CONFLICT (scheduled_slot) DO UPDATE SET
                        status = 'running',
                        attempted_users = 0,
                        delivered_cards = 0,
                        failed_cards = 0,
                        skipped_users = 0,
                        started_at = CURRENT_TIMESTAMP,
                        completed_at = NULL,
                        error_message = ''
                    WHERE CURRENT_TIMESTAMP
                          <= bot_scheduler_runs.scheduled_slot
                             + make_interval(mins => %s)
                      AND (
                          (
                              bot_scheduler_runs.status = 'failed'
                              AND COALESCE(
                                  bot_scheduler_runs.completed_at,
                                  bot_scheduler_runs.started_at
                              ) < CURRENT_TIMESTAMP - INTERVAL '2 minutes'
                          )
                          OR (
                              bot_scheduler_runs.status = 'running'
                              AND bot_scheduler_runs.started_at
                                  < CURRENT_TIMESTAMP - INTERVAL '15 minutes'
                          )
                          OR (
                              bot_scheduler_runs.status = 'completed'
                              AND bot_scheduler_runs.failed_cards > 0
                              AND bot_scheduler_runs.completed_at
                                  < CURRENT_TIMESTAMP - INTERVAL '2 minutes'
                          )
                      )
                    RETURNING scheduled_slot
                    """,
                    (scheduled_slot, grace_minutes),
                )
            ).fetchone()
        return row is not None

    async def finish_scheduler_run(
        self,
        scheduled_slot: datetime,
        *,
        attempted: int,
        delivered: int,
        failed: int,
        skipped: int,
        error_message: str = "",
    ) -> None:
        async with self.pool.connection() as connection:
            await connection.execute(
                """
                UPDATE bot_scheduler_runs
                SET status = %s,
                    attempted_users = %s,
                    delivered_cards = %s,
                    failed_cards = %s,
                    skipped_users = %s,
                    error_message = %s,
                    completed_at = CURRENT_TIMESTAMP
                WHERE scheduled_slot = %s
                """,
                (
                    "failed" if error_message else "completed",
                    attempted,
                    delivered,
                    failed,
                    skipped,
                    error_message[:2000],
                    scheduled_slot,
                ),
            )

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
                               WHERE cards.status = 'delivered'
                           ) AS delivered_cards,
                           max(cards.delivered_at) FILTER (
                               WHERE cards.status = 'delivered'
                           ) AS last_successful_delivery
                    FROM bot_users AS users
                    LEFT JOIN bot_user_cards AS cards
                      ON cards.telegram_user_id = users.telegram_user_id
                    WHERE users.telegram_user_id = %s
                    GROUP BY users.telegram_user_id
                    """,
                    (telegram_user_id,),
                )
            ).fetchone()
        return dict(row) if row else None

    async def admin_content_summary(self) -> dict[str, int]:
        async with self.pool.connection() as connection:
            row = await (
                await connection.execute(
                    """
                    WITH audio AS (
                        SELECT links.entry_id,
                               bool_or(
                                   links.dialect = 'us'
                                   AND variants.conversion_status = 'prepared'
                                   AND variants.audio_data IS NOT NULL
                                   AND variants.source_sha256 = files.sha256
                               ) AS has_us_audio,
                               bool_or(
                                   links.dialect = 'gb'
                                   AND variants.conversion_status = 'prepared'
                                   AND variants.audio_data IS NOT NULL
                                   AND variants.source_sha256 = files.sha256
                               ) AS has_gb_audio
                        FROM oald_entry_audio_sources AS links
                        JOIN oald_audio_files AS files
                          ON files.source_url = links.source_url
                        LEFT JOIN oald_audio_variants AS variants
                          ON variants.source_url = files.source_url
                         AND variants.variant_type = 'telegram_voice_opus'
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
                                  entries.translations #>> '{ru,main}', ''
                              )) <> ''
                              OR CASE
                                  WHEN jsonb_typeof(
                                      entries.translations #> '{ru,also}'
                                  ) = 'array'
                                  THEN jsonb_array_length(
                                      entries.translations #> '{ru,also}'
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
        if selected not in {"us", "gb", "both"}:
            return None
        return _card_from_row(row, dialect=selected, history_id=0)
