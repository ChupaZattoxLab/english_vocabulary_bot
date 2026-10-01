"""Admin panel query helpers."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa

from tgbot.db.models import (
    AdminUser,
    AudienceStats,
    Card,
    DialectPreference,
    admin_user_from_row,
    card_from_row,
)
from tgbot.db.models.audience_stats import audience_stats_from_row
from tgbot.db.queries.base import (
    DbSession,
    mapping_all,
    mapping_exactly_one,
    mapping_first,
)
from tgbot.db.queries.cards import card_content_select, hydrate_card_audio
from tgbot.db.tables import bot_user_cards, bot_users, oald_entries
from tgbot.db.types import CardStatus


class AdminQueries(DbSession):
    async def get_audience_stats(
        self,
        today_start: datetime,
        week_start: datetime,
        month_start: datetime,
    ) -> AudienceStats:
        """Admin overview: totals, new users, and level/dialect breakdowns."""
        async with self.connect() as connection:
            # Totals: audience size, activity, and recent signups.
            totals = await mapping_exactly_one(
                connection,
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
                ).select_from(bot_users),
            )

            # CEFR level breakdown among onboarded users.
            level = sa.func.unnest(bot_users.c.selected_levels).label("level")
            levels = await mapping_all(
                connection,
                sa.select(level, sa.func.count().label("users"))
                .where(bot_users.c.onboarding_completed.is_(True))
                .group_by(level)
                .order_by(level),
            )

            # Dialect preference breakdown among onboarded users.
            dialects = await mapping_all(
                connection,
                sa.select(
                    bot_users.c.dialect,
                    sa.func.count().label("users"),
                )
                .where(bot_users.c.onboarding_completed.is_(True))
                .group_by(bot_users.c.dialect)
                .order_by(bot_users.c.dialect),
            )

        return audience_stats_from_row(totals, levels, dialects)

    async def get_admin_user(
        self,
        telegram_user_id: int,
    ) -> AdminUser | None:
        """User row plus delivered-card count and last successful delivery time."""
        delivered = bot_user_cards.c.status == CardStatus.DELIVERED
        row = await self.fetch_first(
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

        return admin_user_from_row(row) if row else None

    async def get_word_matches(
        self,
        word: str,
        limit: int = 10,
    ) -> tuple[Card, ...]:
        """Exact US/GB spelling hits for /word when several POS/entries exist."""
        rows = await self.fetch_all(
            sa.select(
                oald_entries.c.id.label("entry_id"),
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

        return tuple(card_from_row(row) for row in rows)

    async def get_preview_card(self, entry_id: int | None = None) -> Card | None:
        """Card with both US and GB audio for admin QA (no bot_user_cards row).

        With ``entry_id`` — that entry. Without — a random card, preferring
        spelling differences like color/colour.
        """
        stmt, us_audio, gb_audio = card_content_select()
        both_audio = sa.and_(
            us_audio.c.source_url.is_not(None),
            gb_audio.c.source_url.is_not(None),
        )

        # Specific oald_entries.id, or a random complex spelling pair.
        if entry_id is not None:
            stmt = stmt.where(oald_entries.c.id == entry_id, both_audio)
        else:
            stmt = stmt.where(both_audio).order_by(
                (oald_entries.c.word_us != oald_entries.c.word_gb).desc(),
                sa.func.random(),
            )

        stmt = stmt.limit(1)

        async with self.connect() as connection:
            row = await mapping_first(connection, stmt)
            if not row:
                return None

            # Fetch voice blobs for both dialects after the metadata row is chosen.
            data = dict(row)
            await hydrate_card_audio(connection, data, DialectPreference.BOTH)

        return card_from_row(data)
