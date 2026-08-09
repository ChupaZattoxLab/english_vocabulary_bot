"""Three-times-daily, restart-safe card scheduling."""

from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot

from tgbot.bot_config import BotConfig
from tgbot.constants import (
    DELIVERY_STATUS_DELIVERED,
    DELIVERY_STATUS_FAILED,
    DELIVERY_STATUS_SKIPPED,
    SCHEDULE_GRACE_MINUTES,
)
from tgbot.db import Database
from tgbot.delivery.service import CardDeliveryService
from tgbot.models import ActiveUser

LOGGER = logging.getLogger("tgbot.scheduler")


class CardScheduler:
    def __init__(
        self,
        db: Database,
        delivery: CardDeliveryService,
        config: BotConfig,
    ):
        self.db = db
        self.delivery = delivery
        self.config = config
        self._stop_event = asyncio.Event()

    def stop(self) -> None:
        self._stop_event.set()

    async def run(self, bot: Bot) -> None:
        LOGGER.info(
            "Scheduler started: %s",
            self.config.schedule.text,
        )
        while not self._stop_event.is_set():
            try:
                now = datetime.now(UTC)
                for scheduled_slot in due_schedule_slots(
                    now,
                    timezone_value=self.config.schedule.timezone,
                    send_times=self.config.schedule.send_times,
                ):
                    await self.run_slot(bot, scheduled_slot)

            except Exception:  # noqa: BLE001
                LOGGER.exception("Scheduler iteration failed; it will retry")

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.config.schedule.poll_seconds,
                )
            except TimeoutError:
                continue

        LOGGER.info("Scheduler stopped")

    async def run_slot(self, bot: Bot, scheduled_slot: datetime) -> None:
        claimed = await self.db.claim_scheduler_run(scheduled_slot)
        if not claimed:
            return

        LOGGER.info("Starting scheduled delivery slot %s", scheduled_slot.isoformat())
        attempted = delivered = failed = skipped = 0
        error_message = ""

        try:
            users = await self.db.get_active_users()
            attempted = len(users)
            semaphore = asyncio.Semaphore(self.config.schedule.delivery_concurrency)
            statuses = await asyncio.gather(
                *(
                    self._deliver_to_user(
                        bot,
                        user,
                        scheduled_slot,
                        semaphore,
                    )
                    for user in users
                )
            )
            counts = Counter(statuses)
            delivered = counts[DELIVERY_STATUS_DELIVERED]
            failed = counts[DELIVERY_STATUS_FAILED]
            skipped = counts[DELIVERY_STATUS_SKIPPED]

        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)
            LOGGER.exception("Scheduled slot %s failed", scheduled_slot.isoformat())

        finally:
            await self.db.finish_scheduler_run(
                scheduled_slot,
                attempted_users=attempted,
                delivered_cards=delivered,
                failed_cards=failed,
                skipped_users=skipped,
                error_message=error_message,
            )

        LOGGER.info(
            "Scheduled slot complete: attempted=%s delivered=%s failed=%s skipped=%s",
            attempted,
            delivered,
            failed,
            skipped,
        )

    async def _deliver_to_user(
        self,
        bot: Bot,
        user: ActiveUser,
        scheduled_slot: datetime,
        semaphore: asyncio.Semaphore,
    ) -> str:
        async with semaphore:
            try:
                outcome = await self.delivery.deliver(
                    bot,
                    telegram_user_id=user.telegram_user_id,
                    scheduled_slot=scheduled_slot,
                )
                return outcome.status

            except Exception:  # noqa: BLE001
                LOGGER.exception(
                    "Unexpected scheduled delivery error for user %s",
                    user.telegram_user_id,
                )
                return DELIVERY_STATUS_FAILED


def due_schedule_slots(
    now: datetime,
    timezone_value: ZoneInfo,
    send_times: tuple[time, ...],
) -> tuple[datetime, ...]:
    """Return due UTC slots inside the grace window, including yesterday."""
    local_now = now.astimezone(timezone_value)
    grace = timedelta(minutes=SCHEDULE_GRACE_MINUTES)
    candidate_dates = (local_now.date() - timedelta(days=1), local_now.date())
    slots: list[datetime] = []

    for candidate_date in candidate_dates:
        for send_time in send_times:
            local_slot = datetime.combine(
                candidate_date,
                send_time,
                tzinfo=timezone_value,
            )
            if local_slot <= local_now <= local_slot + grace:
                slots.append(local_slot.astimezone(UTC))

    return tuple(sorted(slots))
