"""Card reservation, delivery history, and Telegram audio-file cache."""

from __future__ import annotations

from collections.abc import MutableMapping
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy import FromClause, Select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncConnection

from tgbot.db.models import (
    VALID_ENGLISH_VARIETY_PREFERENCES,
    Card,
    EnglishVariety,
    EnglishVarietyPreference,
    card_from_row,
)
from tgbot.db.models.user import user_from_row
from tgbot.db.queries.base import DbSession, mapping_first
from tgbot.db.tables import (
    bot_telegram_audio_cache,
    bot_user_cards,
    bot_users,
    oald_audio_files,
    oald_audio_variants,
    oald_entries,
    oald_entry_audio_sources,
)
from tgbot.db.types import (
    CARD_OCCUPIED_STATUSES,
    CARD_RESERVATION_TIMEOUT_MINUTES,
    ERROR_MESSAGE_MAX_LEN,
    ERROR_TYPE_MAX_LEN,
    ERROR_TYPE_STALE_RESERVATION,
    AudioConversionStatus,
    CardStatus,
)


class CardsQueries(DbSession):
    async def reserve_card(
        self,
        telegram_user_id: int,
        scheduled_slot: datetime | None = None,
    ) -> Card | None:
        """Pick and lock a card for delivery; None if nothing can be reserved.

        ``scheduled_slot`` set → scheduler path (user must be active).
        ``scheduled_slot`` omitted → manual /card (allowed while paused); the
        row still stores ``now()`` as the slot for uniqueness.
        """
        # Scheduled delivery requires an active user; /card passes no slot.
        require_active = scheduled_slot is not None
        slot = scheduled_slot if scheduled_slot is not None else datetime.now(UTC)

        async with self.begin() as connection:
            # Serialize reservations for this Telegram user.
            await connection.execute(
                sa.select(sa.func.pg_advisory_xact_lock(telegram_user_id))
            )

            # Expire reservations that never finished delivery.
            await connection.execute(
                sa.update(bot_user_cards)
                .where(
                    bot_user_cards.c.telegram_user_id == telegram_user_id,
                    bot_user_cards.c.status == CardStatus.RESERVED,
                    bot_user_cards.c.created_at
                    < sa.func.current_timestamp()
                    - timedelta(minutes=CARD_RESERVATION_TIMEOUT_MINUTES),
                )
                .values(
                    status=CardStatus.FAILED,
                    error_type=ERROR_TYPE_STALE_RESERVATION,
                    error_message=("reservation timed out before delivery finished"),
                )
            )

            # Load delivery preferences for this user.
            user_row = await mapping_first(
                connection,
                sa.select(bot_users).where(
                    bot_users.c.telegram_user_id == telegram_user_id
                ),
            )
            if not user_row:
                return None

            user = user_from_row(user_row)
            if (
                not user.onboarding_completed
                or not user.settings.selected_levels
                or user.settings.english_variety
                not in VALID_ENGLISH_VARIETY_PREFERENCES
                or (require_active and not user.is_active)
            ):
                return None

            preference = cast(EnglishVarietyPreference, user.settings.english_variety)

            # One occupied card per scheduled slot.
            existing = await mapping_first(
                connection,
                sa.select(bot_user_cards.c.status).where(
                    bot_user_cards.c.telegram_user_id == telegram_user_id,
                    bot_user_cards.c.scheduled_slot == slot,
                    bot_user_cards.c.status.in_(CARD_OCCUPIED_STATUSES),
                ),
            )
            if existing:
                return None

            # Pick a random unseen entry that has prepared audio for the preference.
            levels = list(user.settings.selected_levels)
            stmt, us_audio, gb_audio = card_content_select()
            stmt = (
                stmt.where(
                    oald_entries.c.cefr.in_(levels),
                    preference_audio_ready(preference, us_audio, gb_audio),
                    ~sa.exists(
                        sa.select(sa.literal(1)).where(
                            bot_user_cards.c.telegram_user_id == telegram_user_id,
                            bot_user_cards.c.entry_id == oald_entries.c.id,
                            bot_user_cards.c.status.in_(CARD_OCCUPIED_STATUSES),
                        )
                    ),
                )
                .order_by(sa.func.random())
                .limit(1)
            )

            row = await mapping_first(connection, stmt)
            if not row:
                return None

            # Load voice blobs only for the English varieties we will send.
            card_row = dict(row)
            await hydrate_card_audio(connection, card_row, preference)

            source_url = card_row[
                "gb_source_url"
                if preference == EnglishVarietyPreference.GB
                else "us_source_url"
            ]
            source_url_gb = (
                card_row["gb_source_url"]
                if preference == EnglishVarietyPreference.BOTH
                else None
            )

            # Persist the reservation before returning the card payload.
            user_card = await mapping_first(
                connection,
                sa.insert(bot_user_cards)
                .values(
                    telegram_user_id=telegram_user_id,
                    entry_id=int(card_row["entry_id"]),
                    english_variety=preference,
                    source_url=source_url,
                    source_url_gb=source_url_gb,
                    scheduled_slot=slot,
                )
                .returning(bot_user_cards.c.id),
            )
            if user_card is None:
                return None

            return card_from_row(
                card_row,
                preference=preference,
                user_card_id=int(user_card["id"]),
            )

    async def finish_delivery(
        self,
        user_card_id: int,
        delivered: bool,
        telegram_message_id: int | None = None,
        error_type: str = "",
        error_message: str = "",
    ) -> None:
        """Close a reserved bot_user_cards row as delivered or failed."""
        await self.execute(
            sa.update(bot_user_cards)
            .where(bot_user_cards.c.id == user_card_id)
            .values(
                status=(CardStatus.DELIVERED if delivered else CardStatus.FAILED),
                telegram_message_id=telegram_message_id,
                error_type=("" if delivered else error_type[:ERROR_TYPE_MAX_LEN]),
                error_message=error_message[:ERROR_MESSAGE_MAX_LEN],
                delivered_at=(sa.func.current_timestamp() if delivered else None),
            )
        )

    async def get_cached_audio_file_id(self, source_url: str) -> str | None:
        """Telegram audio file_id for this source_url, if we uploaded it before."""
        row = await self.fetch_first(
            sa.select(bot_telegram_audio_cache.c.telegram_file_id).where(
                bot_telegram_audio_cache.c.source_url == source_url,
            )
        )
        return str(row["telegram_file_id"]) if row else None

    async def set_cached_audio_file_id(
        self,
        source_url: str,
        telegram_file_id: str,
    ) -> None:
        """Remember Telegram file_id after a successful audio upload."""
        stmt = pg_insert(bot_telegram_audio_cache).values(
            source_url=source_url,
            telegram_file_id=telegram_file_id,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[bot_telegram_audio_cache.c.source_url],
            set_={
                "telegram_file_id": stmt.excluded.telegram_file_id,
                "updated_at": sa.func.current_timestamp(),
            },
        )
        await self.execute(stmt)

    async def clear_cached_audio_file_id(self, source_url: str) -> None:
        """Drop a stale file_id after Telegram rejects it on send."""
        await self.execute(
            sa.delete(bot_telegram_audio_cache).where(
                bot_telegram_audio_cache.c.source_url == source_url,
            )
        )


def card_content_select() -> tuple[Select[Any], FromClause, FromClause]:
    """Shared card SELECT for reserve_card and admin preview.

    Joins oald_entries with US/GB prepared-voice metadata (source URL, position,
    content type, filename) — not audio blobs. Callers filter with the returned
    lateral aliases, then load bytes via hydrate_card_audio so random picks do
    not drag large audio_data through ORDER BY random().
    """
    us_audio = prepared_audio_lateral(EnglishVariety.US)
    gb_audio = prepared_audio_lateral(EnglishVariety.GB)

    statement = sa.select(
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
        us_audio.c.content_type.label("us_content_type"),
        us_audio.c.filename.label("us_filename"),
        gb_audio.c.source_url.label("gb_source_url"),
        gb_audio.c.source_position.label("gb_source_position"),
        gb_audio.c.content_type.label("gb_content_type"),
        gb_audio.c.filename.label("gb_filename"),
    ).select_from(
        oald_entries.outerjoin(us_audio, sa.true()).outerjoin(gb_audio, sa.true())
    )
    return statement, us_audio, gb_audio


def prepared_audio_lateral(english_variety: EnglishVariety) -> FromClause:
    """First prepared telegram-voice row for one English variety of the outer entry.

    LATERAL + LIMIT 1: an entry may have several source URLs; we take the
    earliest by source_position among prepared opus variants. Correlated to
    oald_entries.id via the WHERE on links.entry_id.
    """
    links = oald_entry_audio_sources.alias(f"{english_variety}_links")
    files = oald_audio_files.alias(f"{english_variety}_files")
    voice = oald_audio_variants.alias(f"{english_variety}_voice")

    return (
        sa.select(
            links.c.source_url,
            links.c.source_position,
            voice.c.content_type,
            voice.c.filename,
        )
        .select_from(
            links.join(files, files.c.source_url == links.c.source_url).join(
                voice,
                sa.and_(
                    voice.c.source_url == files.c.source_url,
                    voice.c.conversion_status == AudioConversionStatus.PREPARED,
                    voice.c.source_sha256 == files.c.sha256,
                ),
            )
        )
        .where(
            links.c.entry_id == oald_entries.c.id,
            links.c.english_variety == english_variety,
            voice.c.audio_data.is_not(None),
        )
        .order_by(links.c.source_position)
        .limit(1)
        .lateral()
        .alias(f"{english_variety}_audio")
    )


def preference_audio_ready(
    preference: EnglishVarietyPreference,
    us_audio: FromClause,
    gb_audio: FromClause,
) -> sa.ColumnElement[bool]:
    """WHERE fragment: the required English varieties have a prepared voice row."""
    if preference == EnglishVarietyPreference.US:
        return us_audio.c.source_url.is_not(None)

    if preference == EnglishVarietyPreference.GB:
        return gb_audio.c.source_url.is_not(None)

    return sa.and_(
        us_audio.c.source_url.is_not(None),
        gb_audio.c.source_url.is_not(None),
    )


async def hydrate_card_audio(
    connection: AsyncConnection,
    card_row: MutableMapping[str, object],
    preference: EnglishVarietyPreference,
) -> None:
    """Fetch voice blobs only for the chosen entry after metadata selection.

    Separated from card_content_select so candidate scans stay light; we load
    audio_data for the final source_url(s) only.
    """
    prefixes: list[EnglishVariety] = []
    if preference in {EnglishVarietyPreference.US, EnglishVarietyPreference.BOTH}:
        prefixes.append(EnglishVariety.US)
    if preference in {EnglishVarietyPreference.GB, EnglishVarietyPreference.BOTH}:
        prefixes.append(EnglishVariety.GB)

    for prefix in prefixes:
        source_url = card_row.get(f"{prefix}_source_url")
        if not source_url:
            continue

        audio = await mapping_first(
            connection,
            sa.select(
                oald_audio_variants.c.audio_data,
                oald_audio_variants.c.content_type,
                oald_audio_variants.c.filename,
            ).where(
                oald_audio_variants.c.source_url == source_url,
                oald_audio_variants.c.conversion_status
                == AudioConversionStatus.PREPARED,
                oald_audio_variants.c.audio_data.is_not(None),
            ),
        )
        if audio is None:
            continue

        card_row[f"{prefix}_audio_data"] = audio["audio_data"]
        card_row[f"{prefix}_content_type"] = audio["content_type"]
        card_row[f"{prefix}_filename"] = audio["filename"]
