"""Admin panel query helpers."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa

from tgbot.constants import CARD_STATUS_DELIVERED
from tgbot.db.mappers import (
    admin_user_from_row,
    as_db_row,
    as_db_rows,
    card_from_row,
    row_int,
    row_str,
    word_match_from_row,
)
from tgbot.db.queries.base import EngineBound
from tgbot.db.queries.cards import card_content_select, hydrate_card_audio
from tgbot.db.tables import bot_user_cards, bot_users, oald_entries
from tgbot.models import (
    VALID_DIALECT_PREFERENCES,
    AdminUser,
    AudienceStats,
    Card,
    WordMatch,
)


class AdminQueries(EngineBound):
    async def users_summary(
        self,
        today_start: datetime,
        week_start: datetime,
        month_start: datetime,
    ) -> AudienceStats:
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
                            bot_users.c.dialect,
                            sa.func.count().label("users"),
                        )
                        .where(bot_users.c.onboarding_completed.is_(True))
                        .group_by(bot_users.c.dialect)
                        .order_by(bot_users.c.dialect)
                    )
                )
                .mappings()
                .all()
            )

        totals_row = as_db_row(totals)
        level_rows = as_db_rows(levels)
        dialect_rows = as_db_rows(dialects)

        return AudienceStats(
            total_users=row_int(totals_row, "total_users"),
            active_users=row_int(totals_row, "active_users"),
            paused_users=row_int(totals_row, "paused_users"),
            blocked_users=row_int(totals_row, "blocked_users"),
            new_today=row_int(totals_row, "new_today"),
            new_week=row_int(totals_row, "new_week"),
            new_month=row_int(totals_row, "new_month"),
            levels={row_str(row, "level"): row_int(row, "users") for row in level_rows},
            dialects={
                row_str(row, "dialect"): row_int(row, "users")
                for row in dialect_rows
                if row["dialect"]
            },
        )

    async def get_admin_user(
        self,
        telegram_user_id: int,
    ) -> AdminUser | None:
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

        return admin_user_from_row(as_db_row(row)) if row else None

    async def word_search(
        self,
        word: str,
        limit: int = 10,
    ) -> tuple[WordMatch, ...]:
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

        return tuple(word_match_from_row(as_db_row(row)) for row in as_db_rows(rows))

    async def preview_card(
        self,
        entry_id: int | None = None,
        dialect: str | None = None,
        random_card: bool = False,
    ) -> Card | None:
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

            if selected not in VALID_DIALECT_PREFERENCES:
                return None

            await hydrate_card_audio(connection, data, selected)

        return card_from_row(data, dialect=selected, history_id=0)
