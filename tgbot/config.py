"""Environment-backed configuration for the Telegram vocabulary bot."""

from __future__ import annotations

import os
from collections.abc import Mapping
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

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = Path(__file__).resolve().parent
CARD_TEMPLATE_PATH = PACKAGE_ROOT / "delivery" / "templates" / "card_template.html"
BOTH_CARD_TEMPLATE_PATH = (
    PACKAGE_ROOT / "delivery" / "templates" / "card_template_both.html"
)


class ConfigError(ValueError):
    """Raised when bot configuration is missing or invalid."""


def load_env_file(path: Path) -> None:
    """Load a small KEY=VALUE .env file without overriding real environment."""
    if not path.is_file():
        return
    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ConfigError(f"{path}:{line_number}: expected KEY=VALUE")
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ConfigError(f"{path}:{line_number}: environment key is empty")
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def parse_admin_ids(value: str) -> frozenset[int]:
    if not value.strip():
        return frozenset()
    try:
        result = frozenset(
            int(item.strip()) for item in value.split(",") if item.strip()
        )
    except ValueError as exc:
        raise ConfigError(
            "TELEGRAM_ADMIN_IDS must contain comma-separated integers"
        ) from exc
    if any(admin_id <= 0 for admin_id in result):
        raise ConfigError("TELEGRAM_ADMIN_IDS must contain positive user IDs")
    return result


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
    def from_env(
        cls,
        values: Mapping[str, str] | None = None,
        *,
        require_token: bool = True,
    ) -> BotConfig:
        """Load secrets from env/.env; schedule and paths come from constants."""
        source = os.environ if values is None else values
        token = source.get("TELEGRAM_BOT_TOKEN", "").strip()
        if require_token and not token:
            raise ConfigError("TELEGRAM_BOT_TOKEN is required")
        database_url = source.get("OALD_DATABASE_URL", "").strip()
        if not database_url:
            raise ConfigError("OALD_DATABASE_URL is required")

        try:
            timezone = ZoneInfo(TIMEZONE)
        except ZoneInfoNotFoundError as exc:
            raise ConfigError(f"unknown TIMEZONE {TIMEZONE!r}") from exc

        return cls(
            bot_token=token,
            database_url=database_url,
            admin_ids=parse_admin_ids(source.get("TELEGRAM_ADMIN_IDS", "")),
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
