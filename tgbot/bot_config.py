"""Runtime bot configuration assembled from secrets and types."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import time
from typing import Self
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator
from sqlalchemy import make_url

from tgbot.secrets import ConfigError, secrets
from tgbot.types import (
    DB_POOL_SIZE,
    DELIVERY_CONCURRENCY,
    SCHEDULE_GRACE_MINUTES,
    SCHEDULER_POLL_SECONDS,
    SEND_TIMES,
    TIMEZONE,
)


class ScheduleSettings(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    timezone: ZoneInfo
    send_times: tuple[time, ...]
    text: str
    poll_seconds: int
    delivery_concurrency: int
    grace_minutes: int

    @classmethod
    def load(cls) -> Self:
        send_times = parse_send_times(SEND_TIMES)
        return cls(
            timezone=ZoneInfo(TIMEZONE),
            send_times=send_times,
            text=f"{', '.join(sorted(SEND_TIMES))} ({TIMEZONE})",
            poll_seconds=SCHEDULER_POLL_SECONDS,
            delivery_concurrency=DELIVERY_CONCURRENCY,
            grace_minutes=SCHEDULE_GRACE_MINUTES,
        )


class BotConfig(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    bot_token: str
    db_url: str
    db_pool_size: int
    schedule: ScheduleSettings

    @field_validator("bot_token")
    @classmethod
    def require_bot_token(cls, value: str) -> str:
        if not value:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        return value

    @field_validator("db_url")
    @classmethod
    def require_db_url(cls, value: str) -> str:
        if not value:
            raise ValueError("OALD_DATABASE_URL is required")

        url = make_url(value)
        if url.host == "localhost":
            # Avoid IPv6 localhost surprises on Windows.
            url = url.set(host="127.0.0.1")

        return url.render_as_string()

    @classmethod
    def load(cls) -> Self:
        """Build runtime config from the module ``secrets`` singleton."""
        try:
            return cls(
                bot_token=secrets.telegram_bot_token,
                db_url=secrets.db_url,
                db_pool_size=DB_POOL_SIZE,
                schedule=ScheduleSettings.load(),
            )
        except ValidationError as exc:
            message = str(exc.errors()[0].get("msg", exc))
            if message.startswith("Value error, "):
                message = message.removeprefix("Value error, ")
            raise ConfigError(message) from exc


def parse_send_times(values: Sequence[str] = SEND_TIMES) -> tuple[time, ...]:
    return tuple(sorted(time.fromisoformat(value) for value in values))
