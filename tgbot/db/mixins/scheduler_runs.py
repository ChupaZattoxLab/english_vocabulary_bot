"""Scheduler run claim/finish helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, cast

from tgbot.constants import (
    ERROR_MESSAGE_MAX_LEN,
    SCHEDULE_GRACE_MINUTES,
    SCHEDULER_RETRY_COOLDOWN_MINUTES,
    SCHEDULER_STALE_RUNNING_MINUTES,
    SCHEDULER_STATUS_COMPLETED,
    SCHEDULER_STATUS_FAILED,
    SCHEDULER_STATUS_RUNNING,
)
from tgbot.db.mixins.base import PoolBound


class SchedulerMixin(PoolBound):
    async def claim_scheduler_run(
        self,
        scheduled_slot: datetime,
        grace_minutes: int = SCHEDULE_GRACE_MINUTES,
    ) -> bool:
        """Claim a slot, or reclaim it for retries within the grace window."""
        async with self.pool.connection() as connection:
            row = await (
                await connection.execute(
                    cast(
                        Any,
                        f"""
                    INSERT INTO bot_scheduler_runs (scheduled_slot)
                    VALUES (%s)
                    ON CONFLICT (scheduled_slot) DO UPDATE SET
                        status = '{SCHEDULER_STATUS_RUNNING}',
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
                              bot_scheduler_runs.status = '{SCHEDULER_STATUS_FAILED}'
                              AND COALESCE(
                                  bot_scheduler_runs.completed_at,
                                  bot_scheduler_runs.started_at
                              ) < CURRENT_TIMESTAMP
                                  - make_interval(
                                      mins => {SCHEDULER_RETRY_COOLDOWN_MINUTES}
                                  )
                          )
                          OR (
                              bot_scheduler_runs.status = '{SCHEDULER_STATUS_RUNNING}'
                              AND bot_scheduler_runs.started_at
                                  < CURRENT_TIMESTAMP
                                      - make_interval(
                                          mins => {SCHEDULER_STALE_RUNNING_MINUTES}
                                      )
                          )
                          OR (
                              bot_scheduler_runs.status
                                  = '{SCHEDULER_STATUS_COMPLETED}'
                              AND bot_scheduler_runs.failed_cards > 0
                              AND bot_scheduler_runs.completed_at
                                  < CURRENT_TIMESTAMP
                                      - make_interval(
                                          mins => {SCHEDULER_RETRY_COOLDOWN_MINUTES}
                                      )
                          )
                      )
                    RETURNING scheduled_slot
                    """,
                    ),
                    (scheduled_slot, grace_minutes),
                )
            ).fetchone()

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
                    (
                        SCHEDULER_STATUS_FAILED
                        if error_message
                        else SCHEDULER_STATUS_COMPLETED
                    ),
                    attempted,
                    delivered,
                    failed,
                    skipped,
                    error_message[:ERROR_MESSAGE_MAX_LEN],
                    scheduled_slot,
                ),
            )
