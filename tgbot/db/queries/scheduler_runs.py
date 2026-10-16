"""Scheduler run claim/finish helpers."""

from __future__ import annotations

from datetime import datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from tgbot.db.queries.base import DbSession
from tgbot.db.tables import bot_scheduler_runs
from tgbot.db.types import (
    ERROR_MESSAGE_MAX_LEN,
    SCHEDULER_RETRY_COOLDOWN_MINUTES,
    SCHEDULER_STALE_RUNNING_MINUTES,
    SchedulerRunStatus,
)


class SchedulerQueries(DbSession):
    async def claim_scheduler_run(
        self,
        scheduled_slot: datetime,
        grace_minutes: int,
    ) -> bool:
        """Try to own a send slot for this process.

        Inserts a running row, or reclaims a failed/stale/partially-failed run
        while still inside ``grace_minutes``. Returns False if another
        worker already holds a fresh claim.
        """
        runs = bot_scheduler_runs

        within_grace = sa.func.current_timestamp() <= (
            runs.c.scheduled_slot + timedelta(minutes=grace_minutes)
        )
        failed_ready = sa.and_(
            runs.c.status == SchedulerRunStatus.FAILED,
            sa.func.coalesce(runs.c.completed_at, runs.c.started_at)
            < sa.func.current_timestamp()
            - timedelta(minutes=SCHEDULER_RETRY_COOLDOWN_MINUTES),
        )
        stale_running = sa.and_(
            runs.c.status == SchedulerRunStatus.RUNNING,
            runs.c.started_at
            < sa.func.current_timestamp()
            - timedelta(minutes=SCHEDULER_STALE_RUNNING_MINUTES),
        )
        completed_with_failures = sa.and_(
            runs.c.status == SchedulerRunStatus.COMPLETED,
            runs.c.failed_cards > 0,
            runs.c.completed_at
            < sa.func.current_timestamp()
            - timedelta(minutes=SCHEDULER_RETRY_COOLDOWN_MINUTES),
        )

        stmt = pg_insert(runs).values(scheduled_slot=scheduled_slot)
        stmt = stmt.on_conflict_do_update(
            index_elements=[runs.c.scheduled_slot],
            set_={
                "status": SchedulerRunStatus.RUNNING,
                "attempted_users": 0,
                "delivered_cards": 0,
                "failed_cards": 0,
                "skipped_users": 0,
                "started_at": sa.func.current_timestamp(),
                "completed_at": None,
                "error_message": "",
            },
            where=sa.and_(
                within_grace,
                sa.or_(failed_ready, stale_running, completed_with_failures),
            ),
        ).returning(runs.c.scheduled_slot)

        return (await self.execute_fetch_first(stmt)) is not None

    async def finish_scheduler_run(
        self,
        scheduled_slot: datetime,
        attempted_users: int,
        delivered_cards: int,
        failed_cards: int,
        skipped_users: int,
        error_message: str = "",
    ) -> None:
        """Mark the slot completed, or failed when ``error_message`` is set."""
        await self.execute(
            sa.update(bot_scheduler_runs)
            .where(bot_scheduler_runs.c.scheduled_slot == scheduled_slot)
            .values(
                status=(
                    SchedulerRunStatus.FAILED
                    if error_message
                    else SchedulerRunStatus.COMPLETED
                ),
                attempted_users=attempted_users,
                delivered_cards=delivered_cards,
                failed_cards=failed_cards,
                skipped_users=skipped_users,
                error_message=error_message[:ERROR_MESSAGE_MAX_LEN],
                completed_at=sa.func.current_timestamp(),
            )
        )
