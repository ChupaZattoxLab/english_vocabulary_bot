"""Root package types and schedule defaults (used only by tgbot root modules)."""

from __future__ import annotations

# Schedule defaults (not env-configurable; change here, not in .env).
SEND_TIMES = ("13:00", "20:00")
TIMEZONE = "Europe/Moscow"  # UTC+3
SCHEDULER_POLL_SECONDS = 20
DELIVERY_CONCURRENCY = 5
SCHEDULE_GRACE_MINUTES = 60

# Passed into Database via BotConfig.db_pool_size.
DB_POOL_SIZE = 5
