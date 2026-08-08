"""Scheduler run claim/finish helpers."""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert

from tgbot.constants import (
    ERROR_MESSAGE_MAX_LEN,
    SCHEDULE_GRACE_MINUTES,
    SCHEDULER_RETRY_COOLDOWN_MINUTES,
    SCHEDULER_STALE_RUNNING_MINUTES,
    SCHEDULER_STATUS_COMPLETED,
    SCHEDULER_STATUS_FAILED,
    SCHEDULER_STATUS_RUNNING,
)
from tgbot.db.mixins.base import EngineBound
from tgbot.db.schema import bot_scheduler_runs


class SchedulerMixin(EngineBound):
    async def claim_scheduler_run(
        self,
        scheduled_slot: datetime,
        grace_minutes: int = SCHEDULE_GRACE_MINUTES,
    ) -> bool:
        """Claim a slot, or reclaim it for retries within the grace window."""
        runs = bot_scheduler_runs
        within_grace = sa.func.current_timestamp() <= (
            runs.c.scheduled_slot + sa.func.make_interval(mins=grace_minutes)
        )
        failed_ready = sa.and_(
            runs.c.status == SCHEDULER_STATUS_FAILED,
            sa.func.coalesce(runs.c.completed_at, runs.c.started_at)
            < sa.func.current_timestamp()
            - sa.func.make_interval(mins=SCHEDULER_RETRY_COOLDOWN_MINUTES),
        )
        stale_running = sa.and_(
            runs.c.status == SCHEDULER_STATUS_RUNNING,
            runs.c.started_at
            < sa.func.current_timestamp()
            - sa.func.make_interval(mins=SCHEDULER_STALE_RUNNING_MINUTES),
        )
        completed_with_failures = sa.and_(
            runs.c.status == SCHEDULER_STATUS_COMPLETED,
            runs.c.failed_cards > 0,
            runs.c.completed_at
            < sa.func.current_timestamp()
            - sa.func.make_interval(mins=SCHEDULER_RETRY_COOLDOWN_MINUTES),
        )

        stmt = pg_insert(runs).values(scheduled_slot=scheduled_slot)
        stmt = stmt.on_conflict_do_update(
            index_elements=[runs.c.scheduled_slot],
            set_={
                "status": SCHEDULER_STATUS_RUNNING,
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

        async with self.engine.begin() as connection:
            row = (await connection.execute(stmt)).mappings().first()

        return row is not None

    async def finish_scheduler_run(
        self,
        scheduled_slot: datetime,
        attempted: int,
        delivered: int,
        failed: int,
        skipped: int,
        error_message: str = "",
    ) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                sa.update(bot_scheduler_runs)
                .where(bot_scheduler_runs.c.scheduled_slot == scheduled_slot)
                .values(
                    status=(
                        SCHEDULER_STATUS_FAILED
                        if error_message
                        else SCHEDULER_STATUS_COMPLETED
                    ),
                    attempted_users=attempted,
                    delivered_cards=delivered,
                    failed_cards=failed,
                    skipped_users=skipped,
                    error_message=error_message[:ERROR_MESSAGE_MAX_LEN],
                    completed_at=sa.func.current_timestamp(),
                )
            )
