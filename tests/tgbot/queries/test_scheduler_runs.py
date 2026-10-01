"""Scheduler run claim / reclaim rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from tests.support import requires_oald_database
from tests.tgbot.queries.conftest import GRACE_MINUTES
from tgbot.db import Database
from tgbot.db.sync import sync_connection


@requires_oald_database
@pytest.mark.asyncio
async def test_scheduler_slot_can_only_be_claimed_once(
    db: Database,
    onboarded_user: dict,
) -> None:
    slot = datetime(2099, 1, 1, tzinfo=UTC) + timedelta(
        seconds=int(onboarded_user["telegram_user_id"] % 10_000)
    )
    onboarded_user["scheduler_slots"].append(slot)

    assert await db.claim_scheduler_run(slot, GRACE_MINUTES) is True
    assert await db.claim_scheduler_run(slot, GRACE_MINUTES) is False

    await db.finish_scheduler_run(
        slot,
        attempted_users=1,
        delivered_cards=1,
        failed_cards=0,
        skipped_users=0,
    )


@requires_oald_database
@pytest.mark.asyncio
async def test_failed_run_is_reclaimed_after_cooldown_within_grace(
    db: Database,
    onboarded_user: dict,
) -> None:
    slot = datetime.now(UTC) - timedelta(minutes=10)
    onboarded_user["scheduler_slots"].append(slot)

    assert await db.claim_scheduler_run(slot, GRACE_MINUTES) is True
    await db.finish_scheduler_run(
        slot,
        attempted_users=1,
        delivered_cards=0,
        failed_cards=1,
        skipped_users=0,
    )
    # Still inside retry cooldown → cannot reclaim yet.
    assert await db.claim_scheduler_run(slot, GRACE_MINUTES) is False

    with sync_connection(onboarded_user["db_url"]) as connection:
        raw = connection.connection.driver_connection
        assert raw is not None
        with raw.cursor() as cursor:
            cursor.execute(
                """
                UPDATE bot_scheduler_runs
                SET completed_at = CURRENT_TIMESTAMP - INTERVAL '3 minutes'
                WHERE scheduled_slot = %s
                """,
                (slot,),
            )

    assert await db.claim_scheduler_run(slot, GRACE_MINUTES) is True
    await db.finish_scheduler_run(
        slot,
        attempted_users=1,
        delivered_cards=1,
        failed_cards=0,
        skipped_users=0,
    )

    with sync_connection(onboarded_user["db_url"]) as connection:
        raw = connection.connection.driver_connection
        assert raw is not None
        with raw.cursor() as cursor:
            cursor.execute(
                """
                UPDATE bot_scheduler_runs
                SET completed_at = CURRENT_TIMESTAMP - INTERVAL '3 minutes'
                WHERE scheduled_slot = %s
                """,
                (slot,),
            )

    # Successful run with zero failures must not be reclaimed.
    assert await db.claim_scheduler_run(slot, GRACE_MINUTES) is False
