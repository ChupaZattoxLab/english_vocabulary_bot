"""Runtime bot configuration assembled from secrets and constants."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import time
from zoneinfo import ZoneInfo

from tgbot.constants import (
    DB_POOL_SIZE,
    DELIVERY_CONCURRENCY,
    SCHEDULER_POLL_SECONDS,
    SEND_TIMES,
    TIMEZONE,
)
from tgbot.secrets import ConfigError, secrets


@dataclass(frozen=True)
class ScheduleSettings:
    timezone: ZoneInfo
    send_times: tuple[time, ...]
    text: str
    poll_seconds: int
    delivery_concurrency: int

    @classmethod
    def load(cls) -> ScheduleSettings:
        send_times = parse_send_times(SEND_TIMES)
        return cls(
            timezone=ZoneInfo(TIMEZONE),
            send_times=send_times,
            text=f"{', '.join(sorted(SEND_TIMES))} ({TIMEZONE})",
            poll_seconds=SCHEDULER_POLL_SECONDS,
            delivery_concurrency=DELIVERY_CONCURRENCY,
        )


@dataclass(frozen=True)
class BotConfig:
    bot_token: str
    db_url: str
    db_pool_size: int
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
            db_url=secrets.db_url,
            db_pool_size=DB_POOL_SIZE,
            schedule=ScheduleSettings.load(),
        )


def parse_send_times(values: Sequence[str] = SEND_TIMES) -> tuple[time, ...]:
    return tuple(sorted(time.fromisoformat(value) for value in values))
