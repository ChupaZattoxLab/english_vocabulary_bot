"""Card reservation, delivery history, and Telegram audio-file cache."""

from __future__ import annotations

import uuid
from collections.abc import Mapping, MutableMapping, Sequence
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
from tgbot.db.models.card import as_uuid, choose_preference_tracks, ipa_at_position
from tgbot.db.models.user import user_from_row
from tgbot.db.queries.base import (
    DbSession,
    mapping_all,
    mapping_exactly_one,
    mapping_first,
)
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
    new_id,
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

            # One variety is the earliest prepared track from the scan above.
            # "Both" picks its pair here, then loads only those voice blobs.
            card_row = dict(row)
            pair_ready = preference == EnglishVarietyPreference.BOTH and (
                await select_card_audio(connection, card_row, preference)
            )
            if not pair_ready:
                await hydrate_card_audio(connection, card_row, preference)

            if preference == EnglishVarietyPreference.GB:
                source_url = reserved_source_url(card_row, EnglishVariety.GB)
            else:
                source_url = reserved_source_url(card_row, EnglishVariety.US)
            source_url_gb = (
                reserved_source_url(card_row, EnglishVariety.GB)
                if preference == EnglishVarietyPreference.BOTH
                else None
            )

            # Persist the reservation before returning the card payload.
            user_card = await mapping_exactly_one(
                connection,
                sa.insert(bot_user_cards)
                .values(
                    id=new_id(),
                    telegram_user_id=telegram_user_id,
                    entry_id=card_row["entry_id"],
                    english_variety=preference,
                    source_url=source_url,
                    source_url_gb=source_url_gb,
                    scheduled_slot=slot,
                )
                .returning(bot_user_cards.c.id),
            )

            return card_from_row(
                card_row,
                preference=preference,
                user_card_id=as_uuid(user_card["id"]),
            )

    async def finish_delivery(
        self,
        user_card_id: uuid.UUID,
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
        """Telegram voice file_id for this source_url, if we uploaded it before."""
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
        """Remember Telegram file_id after a successful voice upload."""
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
    """Earliest prepared voice for one variety of the outer entry.

    LATERAL + LIMIT 1 keeps the random-card scan to one index lookup: it only
    checks that the variety has a prepared track. The pronunciations we send
    are chosen after a single entry is picked.
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


async def select_card_audio(
    connection: AsyncConnection,
    card_row: MutableMapping[str, object],
    preference: EnglishVarietyPreference,
    *,
    all_prepared: bool = False,
) -> bool:
    """Attach pronunciations for this one entry.

    ``all_prepared`` keeps every prepared track in source order so
    ``Card.for_preference`` can choose. Otherwise only the tracks this
    preference sends are loaded. Returns False when a required variety has
    no voice; the caller then uses the lateral fallback.
    """
    varieties = varieties_for(preference)
    rows = await mapping_all(
        connection,
        sa.select(
            oald_entry_audio_sources.c.english_variety,
            oald_entry_audio_sources.c.source_position,
            oald_entry_audio_sources.c.source_url,
        )
        .select_from(
            oald_entry_audio_sources.join(
                oald_audio_files,
                oald_audio_files.c.source_url == oald_entry_audio_sources.c.source_url,
            ).join(
                oald_audio_variants,
                sa.and_(
                    oald_audio_variants.c.source_url == oald_audio_files.c.source_url,
                    oald_audio_variants.c.conversion_status
                    == AudioConversionStatus.PREPARED,
                    oald_audio_variants.c.source_sha256 == oald_audio_files.c.sha256,
                    oald_audio_variants.c.audio_data.is_not(None),
                ),
            )
        )
        .where(
            oald_entry_audio_sources.c.entry_id == as_uuid(card_row["entry_id"]),
            oald_entry_audio_sources.c.english_variety.in_(varieties),
        )
        .order_by(oald_entry_audio_sources.c.source_position),
    )
    chosen = chosen_tracks(
        group_tracks(card_row, rows), preference, all_prepared=all_prepared
    )
    if chosen is None or not selection_ready(preference, chosen):
        return False

    urls = [url for tracks in chosen.values() for _position, _ipa, url in tracks]
    blobs = await mapping_all(
        connection,
        sa.select(
            oald_audio_variants.c.source_url,
            oald_audio_variants.c.audio_data,
            oald_audio_variants.c.content_type,
            oald_audio_variants.c.filename,
        ).where(
            oald_audio_variants.c.source_url.in_(urls),
            oald_audio_variants.c.conversion_status == AudioConversionStatus.PREPARED,
            oald_audio_variants.c.audio_data.is_not(None),
        ),
    )
    by_url = {str(row["source_url"]): row for row in blobs}
    selected = {
        variety: audio_payload(tracks, by_url) for variety, tracks in chosen.items()
    }
    if not selection_ready(preference, selected):
        return False

    card_row["selected_us"] = selected[EnglishVariety.US]
    card_row["selected_gb"] = selected[EnglishVariety.GB]
    return True


def reserved_source_url(
    card_row: Mapping[str, object],
    variety: EnglishVariety,
) -> str | None:
    """Source URL stored on the reservation: the first track we will send."""
    selected = card_row.get(f"selected_{variety}")
    if isinstance(selected, list) and selected:
        first = selected[0]
        if isinstance(first, Mapping):
            url = first.get("source_url")
            if url:
                return str(url)

    url = card_row.get(f"{variety}_source_url")
    return str(url) if url else None


def varieties_for(
    preference: EnglishVarietyPreference,
) -> tuple[EnglishVariety, ...]:
    if preference == EnglishVarietyPreference.US:
        return (EnglishVariety.US,)
    if preference == EnglishVarietyPreference.GB:
        return (EnglishVariety.GB,)
    return (EnglishVariety.US, EnglishVariety.GB)


def group_tracks(
    card_row: Mapping[str, object],
    rows: Sequence[Mapping[Any, Any]],
) -> dict[EnglishVariety, list[tuple[int, str, str]]]:
    grouped: dict[EnglishVariety, list[tuple[int, str, str]]] = {
        EnglishVariety.US: [],
        EnglishVariety.GB: [],
    }
    for row in rows:
        variety = EnglishVariety(str(row["english_variety"]))
        position = int(row["source_position"])
        ipa_key = "ipa_us" if variety == EnglishVariety.US else "ipa_gb"
        grouped[variety].append(
            (
                position,
                ipa_at_position(card_row.get(ipa_key), position),
                str(row["source_url"]),
            )
        )
    for tracks in grouped.values():
        tracks.sort(key=lambda track: track[0])
    return grouped


def chosen_tracks(
    grouped: dict[EnglishVariety, list[tuple[int, str, str]]],
    preference: EnglishVarietyPreference,
    *,
    all_prepared: bool,
) -> dict[EnglishVariety, list[tuple[int, str, str]]] | None:
    if all_prepared:
        return grouped

    us_tracks = grouped[EnglishVariety.US]
    gb_tracks = grouped[EnglishVariety.GB]
    chosen = choose_preference_tracks(
        preference,
        [ipa for _position, ipa, _url in us_tracks],
        [ipa for _position, ipa, _url in gb_tracks],
    )
    if chosen is None:
        return None

    us_index, gb_index = chosen
    return {
        EnglishVariety.US: [] if us_index is None else [us_tracks[us_index]],
        EnglishVariety.GB: [] if gb_index is None else [gb_tracks[gb_index]],
    }


def selection_ready(
    preference: EnglishVarietyPreference,
    chosen: Mapping[EnglishVariety, Sequence[object]],
) -> bool:
    has_us = bool(chosen[EnglishVariety.US])
    has_gb = bool(chosen[EnglishVariety.GB])
    if preference == EnglishVarietyPreference.US:
        return has_us
    if preference == EnglishVarietyPreference.GB:
        return has_gb
    return has_us and has_gb


def audio_payload(
    tracks: Sequence[tuple[int, str, str]],
    by_url: Mapping[str, Any],
) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for _position, ipa, url in tracks:
        audio = by_url.get(url)
        if audio is None:
            continue
        payload.append(
            {
                "ipa": ipa,
                "source_url": url,
                "audio_data": audio["audio_data"],
                "content_type": audio["content_type"],
                "filename": audio["filename"],
            }
        )
    return payload
