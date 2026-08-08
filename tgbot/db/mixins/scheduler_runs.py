"""Scheduler run claim/finish helpers."""

from __future__ import annotations

from datetime import datetime

from tgbot.db.mixins.base import PoolBound


class SchedulerMixin(PoolBound):
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
