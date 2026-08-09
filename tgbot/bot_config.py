"""Runtime bot configuration assembled from secrets and constants."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

from tgbot.constants import (
    DATABASE_POOL_SIZE,
    DELIVERY_CONCURRENCY,
    SCHEDULE_GRACE_MINUTES,
    SCHEDULER_POLL_SECONDS,
    SEND_TIMES,
    TIMEZONE,
)
from tgbot.secrets import ConfigError, secrets


@dataclass(frozen=True)
class BotConfig:
    bot_token: str
    database_url: str
    admin_ids: frozenset[int]
    database_pool_size: int
    schedule: ScheduleSettings

    @classmethod
    def load(cls) -> BotConfig:
        """Build runtime config from the module ``secrets`` singleton."""
        if not secrets.telegram_bot_token:
            raise ConfigError("TELEGRAM_BOT_TOKEN is required")

        if not secrets.db_url:
            raise ConfigError("OALD_DATABASE_URL is required")

        return cls(
            bot_token=secrets.telegram_bot_token,
            database_url=secrets.db_url,
            admin_ids=secrets.admin_ids,
            database_pool_size=DATABASE_POOL_SIZE,
            schedule=ScheduleSettings.load(),
        )


@dataclass(frozen=True)
class ScheduleSettings:
    timezone: ZoneInfo
    send_times: tuple[time, ...]
    text: str
    grace_minutes: int
    poll_seconds: int
    delivery_concurrency: int

    @classmethod
    def load(cls) -> ScheduleSettings:
        send_times = parse_send_times(SEND_TIMES)
        return cls(
            timezone=ZoneInfo(TIMEZONE),
            send_times=send_times,
            text=f"{', '.join(sorted(SEND_TIMES))} ({TIMEZONE})",
            grace_minutes=SCHEDULE_GRACE_MINUTES,
            poll_seconds=SCHEDULER_POLL_SECONDS,
            delivery_concurrency=DELIVERY_CONCURRENCY,
        )


def parse_send_times(values: Sequence[str] = SEND_TIMES) -> tuple[time, ...]:
    return tuple(sorted(time.fromisoformat(value) for value in values))
