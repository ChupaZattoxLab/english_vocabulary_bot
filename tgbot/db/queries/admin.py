"""Admin panel query helpers."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa

from tgbot.constants import (
    AUDIO_CONVERSION_PREPARED,
    AUDIO_VARIANT_TELEGRAM_VOICE_OPUS,
    CARD_STATUS_DELIVERED,
)
from tgbot.db.queries.base import EngineBound
from tgbot.db.queries.cards import card_content_select, hydrate_card_audio
from tgbot.db.models import (
    VALID_PRONUNCIATIONS,
    AdminContentSummary,
    AdminUserDetail,
    AdminUsersSummary,
    AdminWordMatch,
    ReservedCard,
    admin_user_detail_from_row,
    admin_word_match_from_row,
    as_db_row,
    as_db_rows,
    card_from_row,
    row_int,
    row_str,
)
from tgbot.db.schema import (
    bot_user_cards,
    bot_users,
    oald_audio_files,
    oald_audio_variants,
    oald_entries,
    oald_entry_audio_sources,
)


class AdminQueries(EngineBound):
    async def admin_users_summary(
        self,
        today_start: datetime,
        week_start: datetime,
        month_start: datetime,
    ) -> AdminUsersSummary:
        async with self.engine.connect() as connection:
            totals = (
                (
                    await connection.execute(
                        sa.select(
                            sa.func.count().label("total_users"),
                            sa.func.count()
                            .filter(
                                sa.and_(
                                    bot_users.c.is_active.is_(True),
                                    bot_users.c.onboarding_completed.is_(True),
                                )
                            )
                            .label("active_users"),
                            sa.func.count()
                            .filter(
                                sa.and_(
                                    bot_users.c.paused_at.is_not(None),
                                    bot_users.c.blocked_at.is_(None),
                                )
                            )
                            .label("paused_users"),
                            sa.func.count()
                            .filter(bot_users.c.blocked_at.is_not(None))
                            .label("blocked_users"),
                            sa.func.count()
                            .filter(bot_users.c.created_at >= today_start)
                            .label("new_today"),
                            sa.func.count()
                            .filter(bot_users.c.created_at >= week_start)
                            .label("new_week"),
                            sa.func.count()
                            .filter(bot_users.c.created_at >= month_start)
                            .label("new_month"),
                        ).select_from(bot_users)
                    )
                )
                .mappings()
                .one()
            )

            level = sa.func.unnest(bot_users.c.selected_levels).label("level")
            levels = (
                (
                    await connection.execute(
                        sa.select(level, sa.func.count().label("users"))
                        .where(bot_users.c.onboarding_completed.is_(True))
                        .group_by(level)
                        .order_by(level)
                    )
                )
                .mappings()
                .all()
            )

            dialects = (
                (
                    await connection.execute(
                        sa.select(
                            bot_users.c.pronunciation,
                            sa.func.count().label("users"),
                        )
                        .where(bot_users.c.onboarding_completed.is_(True))
                        .group_by(bot_users.c.pronunciation)
                        .order_by(bot_users.c.pronunciation)
                    )
                )
                .mappings()
                .all()
            )

        totals_row = as_db_row(totals)
        level_rows = as_db_rows(levels)
        dialect_rows = as_db_rows(dialects)

        return AdminUsersSummary(
            total_users=row_int(totals_row, "total_users"),
            active_users=row_int(totals_row, "active_users"),
            paused_users=row_int(totals_row, "paused_users"),
            blocked_users=row_int(totals_row, "blocked_users"),
            new_today=row_int(totals_row, "new_today"),
            new_week=row_int(totals_row, "new_week"),
            new_month=row_int(totals_row, "new_month"),
            levels={row_str(row, "level"): row_int(row, "users") for row in level_rows},
            dialects={
                row_str(row, "pronunciation"): row_int(row, "users")
                for row in dialect_rows
                if row["pronunciation"]
            },
        )

    async def admin_user_detail(
        self,
        telegram_user_id: int,
    ) -> AdminUserDetail | None:
        delivered = bot_user_cards.c.status == CARD_STATUS_DELIVERED
        stmt = (
            sa.select(
                bot_users,
                sa.func.count(bot_user_cards.c.id)
                .filter(delivered)
                .label("delivered_cards"),
                sa.func.max(bot_user_cards.c.delivered_at)
                .filter(delivered)
                .label("last_successful_delivery"),
            )
            .outerjoin(
                bot_user_cards,
                bot_user_cards.c.telegram_user_id == bot_users.c.telegram_user_id,
            )
            .where(bot_users.c.telegram_user_id == telegram_user_id)
            .group_by(bot_users.c.telegram_user_id)
        )

        async with self.engine.connect() as connection:
            row = (await connection.execute(stmt)).mappings().first()

        return admin_user_detail_from_row(as_db_row(row)) if row else None

    async def admin_content_summary(self) -> AdminContentSummary:
        links = oald_entry_audio_sources
        files = oald_audio_files
        variants = oald_audio_variants

        audio = (
            sa.select(
                links.c.entry_id,
                sa.func.bool_or(
                    sa.and_(
                        links.c.dialect == "us",
                        variants.c.conversion_status == AUDIO_CONVERSION_PREPARED,
                        variants.c.audio_data.is_not(None),
                        variants.c.source_sha256 == files.c.sha256,
                    )
                ).label("has_us_audio"),
                sa.func.bool_or(
                    sa.and_(
                        links.c.dialect == "gb",
                        variants.c.conversion_status == AUDIO_CONVERSION_PREPARED,
                        variants.c.audio_data.is_not(None),
                        variants.c.source_sha256 == files.c.sha256,
                    )
                ).label("has_gb_audio"),
            )
            .select_from(
                links.join(files, files.c.source_url == links.c.source_url).outerjoin(
                    variants,
                    sa.and_(
                        variants.c.source_url == files.c.source_url,
                        variants.c.variant_type == AUDIO_VARIANT_TELEGRAM_VOICE_OPUS,
                    ),
                )
            )
            .group_by(links.c.entry_id)
            .cte("audio")
        )

        ru_main = oald_entries.c.translations["ru"]["main"].as_string()
        ru_also = oald_entries.c.translations["ru"]["also"]
        has_translation = sa.or_(
            sa.func.btrim(sa.func.coalesce(ru_main, "")) != "",
            sa.and_(
                sa.func.jsonb_typeof(ru_also) == "array",
                sa.func.jsonb_array_length(ru_also) > 0,
            ),
        )
        ready = sa.and_(
            oald_entries.c.is_active.is_(True),
            sa.func.btrim(oald_entries.c.word_us) != "",
            sa.func.btrim(oald_entries.c.word_gb) != "",
            sa.func.btrim(oald_entries.c.lexical_category) != "",
            sa.func.btrim(oald_entries.c.definition) != "",
            sa.func.btrim(oald_entries.c.example) != "",
            has_translation,
            sa.or_(
                sa.and_(
                    sa.func.cardinality(oald_entries.c.ipa_us) > 0,
                    sa.func.coalesce(audio.c.has_us_audio, False),
                ),
                sa.and_(
                    sa.func.cardinality(oald_entries.c.ipa_gb) > 0,
                    sa.func.coalesce(audio.c.has_gb_audio, False),
                ),
            ),
        )

        stmt = sa.select(
            sa.func.count().filter(ready).label("ready_entries")
        ).select_from(
            oald_entries.outerjoin(audio, audio.c.entry_id == oald_entries.c.id)
        )

        async with self.engine.connect() as connection:
            row = (await connection.execute(stmt)).mappings().one()

        return AdminContentSummary(
            ready_entries=row_int(as_db_row(row), "ready_entries")
        )

    async def admin_word_search(
        self,
        word: str,
        limit: int = 10,
    ) -> tuple[AdminWordMatch, ...]:
        stmt = (
            sa.select(
                oald_entries.c.id,
                oald_entries.c.word_us,
                oald_entries.c.word_gb,
                oald_entries.c.lexical_category,
                oald_entries.c.cefr,
            )
            .where(
                sa.or_(
                    sa.func.lower(oald_entries.c.word_us) == sa.func.lower(word),
                    sa.func.lower(oald_entries.c.word_gb) == sa.func.lower(word),
                )
            )
            .order_by(oald_entries.c.lexical_category, oald_entries.c.id)
            .limit(limit)
        )

        async with self.engine.connect() as connection:
            rows = (await connection.execute(stmt)).mappings().all()

        return tuple(
            admin_word_match_from_row(as_db_row(row)) for row in as_db_rows(rows)
        )

    async def admin_preview_card(
        self,
        entry_id: int | None = None,
        dialect: str | None = None,
        random_card: bool = False,
    ) -> ReservedCard | None:
        stmt, us_audio, gb_audio = card_content_select(with_audio_data=False)

        if entry_id is not None:
            stmt = stmt.where(oald_entries.c.id == entry_id)
        else:
            stmt = stmt.where(
                oald_entries.c.is_active.is_(True),
                sa.or_(
                    us_audio.c.source_url.is_not(None),
                    gb_audio.c.source_url.is_not(None),
                ),
            )

        stmt = stmt.order_by(
            sa.func.random() if random_card else oald_entries.c.id
        ).limit(1)

        async with self.engine.connect() as connection:
            row = (await connection.execute(stmt)).mappings().first()
            if not row:
                return None

            data = dict(row)
            available_us = data["us_source_url"] is not None
            available_gb = data["gb_source_url"] is not None
            requested = (dialect or "").lower()

            if requested == "both" and not (available_us and available_gb):
                return None

            if requested == "us" and not available_us:
                return None

            if requested == "gb" and not available_gb:
                return None

            selected = requested or (
                "both"
                if available_us and available_gb
                else "us"
                if available_us
                else "gb"
            )

            if selected not in VALID_PRONUNCIATIONS:
                return None

            await hydrate_card_audio(connection, data, selected)

        return card_from_row(data, dialect=selected, history_id=0)
