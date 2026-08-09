"""Card reservation, delivery history, and Telegram audio-file cache."""

from __future__ import annotations

from collections.abc import MutableMapping
from datetime import datetime, timedelta
from typing import Any, Literal

import sqlalchemy as sa
from sqlalchemy import FromClause, Select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

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
from tgbot.db.mappers import (
    as_db_row,
    card_from_row,
    row_bool,
    row_int,
    row_optional_str,
    row_str,
    row_str_sequence,
)
from tgbot.db.queries.base import EngineBound
from tgbot.db.tables import (
    bot_telegram_audio_cache,
    bot_user_cards,
    bot_users,
    oald_audio_files,
    oald_audio_variants,
    oald_entries,
    oald_entry_audio_sources,
)
from tgbot.models import VALID_DIALECT_PREFERENCES, Card

AudioDialect = Literal["us", "gb"]


class CardsQueries(EngineBound):
    async def reserve_card(
        self,
        telegram_user_id: int,
        scheduled_slot: datetime,
        require_active: bool = True,
    ) -> Card | None:
        async with self.engine.begin() as connection:
            await connection.execute(
                sa.select(sa.func.pg_advisory_xact_lock(telegram_user_id))
            )

            await connection.execute(
                sa.update(bot_user_cards)
                .where(
                    bot_user_cards.c.telegram_user_id == telegram_user_id,
                    bot_user_cards.c.status == CARD_STATUS_RESERVED,
                    bot_user_cards.c.created_at
                    < sa.func.current_timestamp()
                    - timedelta(minutes=CARD_RESERVATION_TIMEOUT_MINUTES),
                )
                .values(
                    status=CARD_STATUS_FAILED,
                    error_type=ERROR_TYPE_STALE_RESERVATION,
                    error_message=("reservation timed out before delivery finished"),
                )
            )

            user = (
                (
                    await connection.execute(
                        sa.select(
                            bot_users.c.selected_levels,
                            bot_users.c.dialect,
                            bot_users.c.is_active,
                            bot_users.c.onboarding_completed,
                        ).where(bot_users.c.telegram_user_id == telegram_user_id)
                    )
                )
                .mappings()
                .first()
            )
            if not user:
                return None

            user_row = as_db_row(user)
            dialect = row_optional_str(user_row, "dialect")

            if (
                not row_bool(user_row, "onboarding_completed")
                or not user_row["selected_levels"]
                or dialect not in VALID_DIALECT_PREFERENCES
                or (require_active and not row_bool(user_row, "is_active"))
            ):
                return None

            existing = (
                (
                    await connection.execute(
                        sa.select(bot_user_cards.c.status).where(
                            bot_user_cards.c.telegram_user_id == telegram_user_id,
                            bot_user_cards.c.scheduled_slot == scheduled_slot,
                            bot_user_cards.c.status.in_(CARD_ACTIVE_STATUSES),
                        )
                    )
                )
                .mappings()
                .first()
            )
            if existing:
                return None

            levels = list(row_str_sequence(user_row, "selected_levels"))
            stmt, us_audio, gb_audio = card_content_select(with_audio_data=False)
            stmt = (
                stmt.where(
                    oald_entries.c.is_active.is_(True),
                    oald_entries.c.cefr.in_(levels),
                    dialect_audio_ready(dialect, us_audio, gb_audio),
                    ~sa.exists(
                        sa.select(sa.literal(1)).where(
                            bot_user_cards.c.telegram_user_id == telegram_user_id,
                            bot_user_cards.c.entry_id == oald_entries.c.id,
                            bot_user_cards.c.status.in_(CARD_ACTIVE_STATUSES),
                        )
                    ),
                )
                .order_by(sa.func.random())
                .limit(1)
            )

            row = (await connection.execute(stmt)).mappings().first()
            if not row:
                return None

            card_row = dict(row)
            await hydrate_card_audio(connection, card_row, dialect)

            source_url = card_row[
                "gb_source_url" if dialect == "gb" else "us_source_url"
            ]
            source_url_gb = card_row["gb_source_url"] if dialect == "both" else None

            history = (
                (
                    await connection.execute(
                        sa.insert(bot_user_cards)
                        .values(
                            telegram_user_id=telegram_user_id,
                            entry_id=row_int(as_db_row(card_row), "entry_id"),
                            dialect=dialect,
                            source_url=source_url,
                            source_url_gb=source_url_gb,
                            scheduled_slot=scheduled_slot,
                        )
                        .returning(bot_user_cards.c.id)
                    )
                )
                .mappings()
                .first()
            )
            if history is None:
                return None

            return card_from_row(
                card_row,
                dialect=dialect,
                history_id=row_int(as_db_row(history), "id"),
            )

    async def finish_delivery(
        self,
        history_id: int,
        delivered: bool,
        telegram_message_id: int | None = None,
        error_type: str = "",
        error_message: str = "",
    ) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                sa.update(bot_user_cards)
                .where(bot_user_cards.c.id == history_id)
                .values(
                    status=(CARD_STATUS_DELIVERED if delivered else CARD_STATUS_FAILED),
                    telegram_message_id=telegram_message_id,
                    error_type=("" if delivered else error_type[:ERROR_TYPE_MAX_LEN]),
                    error_message=error_message[:ERROR_MESSAGE_MAX_LEN],
                    delivered_at=(sa.func.current_timestamp() if delivered else None),
                )
            )

    async def cached_audio_file_id(
        self,
        source_url: str,
        send_method: str,
    ) -> str | None:
        async with self.engine.connect() as connection:
            row = (
                (
                    await connection.execute(
                        sa.select(bot_telegram_audio_cache.c.telegram_file_id).where(
                            bot_telegram_audio_cache.c.source_url == source_url,
                            bot_telegram_audio_cache.c.send_method == send_method,
                        )
                    )
                )
                .mappings()
                .first()
            )

        return row_str(as_db_row(row), "telegram_file_id") if row else None

    async def cache_audio_file_id(
        self,
        source_url: str,
        send_method: str,
        telegram_file_id: str,
    ) -> None:
        stmt = pg_insert(bot_telegram_audio_cache).values(
            source_url=source_url,
            send_method=send_method,
            telegram_file_id=telegram_file_id,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[
                bot_telegram_audio_cache.c.source_url,
                bot_telegram_audio_cache.c.send_method,
            ],
            set_={
                "telegram_file_id": stmt.excluded.telegram_file_id,
                "updated_at": sa.func.current_timestamp(),
            },
        )

        async with self.engine.begin() as connection:
            await connection.execute(stmt)

    async def clear_cached_audio_file_id(
        self,
        source_url: str,
        send_method: str,
    ) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                sa.delete(bot_telegram_audio_cache).where(
                    bot_telegram_audio_cache.c.source_url == source_url,
                    bot_telegram_audio_cache.c.send_method == send_method,
                )
            )


def card_content_select(
    with_audio_data: bool = True,
) -> tuple[Select[Any], FromClause, FromClause]:
    """Entry row plus first prepared US/GB telegram-voice audio (LATERAL)."""
    us_audio = prepared_audio_lateral("us", with_audio_data=with_audio_data)
    gb_audio = prepared_audio_lateral("gb", with_audio_data=with_audio_data)

    columns: list[Any] = [
        oald_entries.c.id.label("entry_id"),
        oald_entries.c.word_us,
        oald_entries.c.word_gb,
        oald_entries.c.lexical_category,
        oald_entries.c.cefr,
        oald_entries.c.definition,
        oald_entries.c.example,
        oald_entries.c.ipa_us,
        oald_entries.c.ipa_gb,
        oald_entries.c.translations,
        us_audio.c.source_url.label("us_source_url"),
        us_audio.c.source_position.label("us_source_position"),
    ]
    if with_audio_data:
        columns.append(us_audio.c.audio_data.label("us_audio_data"))
    columns.extend(
        [
            us_audio.c.content_type.label("us_content_type"),
            us_audio.c.filename.label("us_filename"),
            gb_audio.c.source_url.label("gb_source_url"),
            gb_audio.c.source_position.label("gb_source_position"),
        ]
    )
    if with_audio_data:
        columns.append(gb_audio.c.audio_data.label("gb_audio_data"))
    columns.extend(
        [
            gb_audio.c.content_type.label("gb_content_type"),
            gb_audio.c.filename.label("gb_filename"),
        ]
    )

    statement = sa.select(*columns).select_from(
        oald_entries.outerjoin(us_audio, sa.true()).outerjoin(gb_audio, sa.true())
    )

    return statement, us_audio, gb_audio


def prepared_audio_lateral(
    dialect: AudioDialect,
    with_audio_data: bool = True,
) -> FromClause:
    links = oald_entry_audio_sources.alias(f"{dialect}_links")
    files = oald_audio_files.alias(f"{dialect}_files")
    voice = oald_audio_variants.alias(f"{dialect}_voice")

    columns: list[Any] = [
        links.c.source_url,
        links.c.source_position,
    ]
    if with_audio_data:
        columns.append(voice.c.audio_data)
    columns.extend([voice.c.content_type, voice.c.filename])

    return (
        sa.select(*columns)
        .select_from(
            links.join(files, files.c.source_url == links.c.source_url).join(
                voice,
                sa.and_(
                    voice.c.source_url == files.c.source_url,
                    voice.c.variant_type == AUDIO_VARIANT_TELEGRAM_VOICE_OPUS,
                    voice.c.conversion_status == AUDIO_CONVERSION_PREPARED,
                    voice.c.source_sha256 == files.c.sha256,
                ),
            )
        )
        .where(
            links.c.entry_id == oald_entries.c.id,
            links.c.dialect == dialect,
            voice.c.audio_data.is_not(None),
        )
        .order_by(links.c.source_position)
        .limit(1)
        .lateral()
        .alias(f"{dialect}_audio")
    )


def dialect_audio_ready(
    dialect: str,
    us_audio: FromClause,
    gb_audio: FromClause,
) -> sa.ColumnElement[bool]:
    if dialect == "us":
        return us_audio.c.source_url.is_not(None)
    if dialect == "gb":
        return gb_audio.c.source_url.is_not(None)
    if dialect == "both":
        return sa.and_(
            us_audio.c.source_url.is_not(None),
            gb_audio.c.source_url.is_not(None),
        )
    return sa.false()


async def hydrate_card_audio(
    connection: AsyncConnection,
    card_row: MutableMapping[str, object],
    dialect: str,
) -> None:
    """Load prepared telegram-voice blobs for the chosen source URLs only."""
    prefixes: list[str] = []
    if dialect in {"us", "both"}:
        prefixes.append("us")
    if dialect in {"gb", "both"}:
        prefixes.append("gb")

    for prefix in prefixes:
        source_url = card_row.get(f"{prefix}_source_url")
        if not source_url:
            continue

        audio = (
            (
                await connection.execute(
                    sa.select(
                        oald_audio_variants.c.audio_data,
                        oald_audio_variants.c.content_type,
                        oald_audio_variants.c.filename,
                    ).where(
                        oald_audio_variants.c.source_url == source_url,
                        oald_audio_variants.c.variant_type
                        == AUDIO_VARIANT_TELEGRAM_VOICE_OPUS,
                        oald_audio_variants.c.conversion_status
                        == AUDIO_CONVERSION_PREPARED,
                        oald_audio_variants.c.audio_data.is_not(None),
                    )
                )
            )
            .mappings()
            .first()
        )
        if audio is None:
            continue

        card_row[f"{prefix}_audio_data"] = audio["audio_data"]
        card_row[f"{prefix}_content_type"] = audio["content_type"]
        card_row[f"{prefix}_filename"] = audio["filename"]
