"""Runtime bot configuration assembled from secrets and constants."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from tgbot.constants import (
    CARDS_PER_DAY,
    DATABASE_POOL_SIZE,
    DELIVERY_CONCURRENCY,
    SCHEDULE_GRACE_MINUTES,
    SCHEDULER_POLL_SECONDS,
    SEND_TIMES,
    TIMEZONE,
)
from tgbot.secrets import PACKAGE_ROOT, ConfigError, secrets

CARD_TEMPLATE_PATH = PACKAGE_ROOT / "delivery" / "templates" / "card_template.html"
BOTH_CARD_TEMPLATE_PATH = (
    PACKAGE_ROOT / "delivery" / "templates" / "card_template_both.html"
)


@dataclass(frozen=True)
class BotConfig:
    bot_token: str
    database_url: str
    admin_ids: frozenset[int]
    timezone: ZoneInfo
    timezone_name: str
    send_times: tuple[time, ...]
    card_template_path: Path
    both_card_template_path: Path
    schedule_grace_minutes: int
    scheduler_poll_seconds: int
    delivery_concurrency: int
    database_pool_size: int

    @property
    def schedule_text(self) -> str:
        times = ", ".join(item.strftime("%H:%M") for item in self.send_times)
        return f"{times} ({self.timezone_name})"

    @classmethod
    def load(cls) -> BotConfig:
        """Build runtime config from the module ``secrets`` singleton."""
        if not secrets.telegram_bot_token:
            raise ConfigError("TELEGRAM_BOT_TOKEN is required")

        if not secrets.db_url:
            raise ConfigError("OALD_DATABASE_URL is required")

        try:
            timezone = ZoneInfo(TIMEZONE)
        except ZoneInfoNotFoundError as exc:
            raise ConfigError(f"unknown TIMEZONE {TIMEZONE!r}") from exc

        return cls(
            bot_token=secrets.telegram_bot_token,
            database_url=secrets.db_url,
            admin_ids=secrets.admin_ids,
            timezone=timezone,
            timezone_name=TIMEZONE,
            send_times=parse_send_times(SEND_TIMES),
            card_template_path=CARD_TEMPLATE_PATH,
            both_card_template_path=BOTH_CARD_TEMPLATE_PATH,
            schedule_grace_minutes=SCHEDULE_GRACE_MINUTES,
            scheduler_poll_seconds=SCHEDULER_POLL_SECONDS,
            delivery_concurrency=DELIVERY_CONCURRENCY,
            database_pool_size=DATABASE_POOL_SIZE,
        )


def parse_send_times(value: str) -> tuple[time, ...]:
    parsed: list[time] = []
    for item in value.split(","):
        text = item.strip()
        try:
            hour_text, minute_text = text.split(":", 1)
            parsed_time = time(hour=int(hour_text), minute=int(minute_text))
        except (TypeError, ValueError) as exc:
            raise ConfigError(
                "SEND_TIMES must contain HH:MM values separated by commas"
            ) from exc
        parsed.append(parsed_time)

    if len(parsed) != CARDS_PER_DAY or len(set(parsed)) != CARDS_PER_DAY:
        raise ConfigError(
            f"SEND_TIMES must contain exactly {CARDS_PER_DAY} unique times"
        )

    return tuple(sorted(parsed))
