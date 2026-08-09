"""Shared domain and runtime constants for the Telegram bot."""

from __future__ import annotations

# ---------------------------------------------------------------------------
# bot_user_cards.status values and statuses that still "own" a word/slot
# ---------------------------------------------------------------------------

CARD_STATUS_RESERVED = "reserved"
CARD_STATUS_DELIVERED = "delivered"
CARD_STATUS_FAILED = "failed"
CARD_ACTIVE_STATUSES = (CARD_STATUS_DELIVERED, CARD_STATUS_RESERVED)

# ---------------------------------------------------------------------------
# bot_scheduler_runs.status values
# ---------------------------------------------------------------------------

SCHEDULER_STATUS_RUNNING = "running"
SCHEDULER_STATUS_COMPLETED = "completed"
SCHEDULER_STATUS_FAILED = "failed"

# ---------------------------------------------------------------------------
# DeliveryOutcome.status returned by CardDeliveryService / scheduler
# ---------------------------------------------------------------------------

DELIVERY_STATUS_DELIVERED = "delivered"
DELIVERY_STATUS_FAILED = "failed"
DELIVERY_STATUS_SKIPPED = "skipped"

# ---------------------------------------------------------------------------
# Prepared Telegram voice audio (oald_audio_variants + send_voice cache)
# ---------------------------------------------------------------------------

AUDIO_VARIANT_TELEGRAM_VOICE_OPUS = "telegram_voice_opus"
AUDIO_CONVERSION_PREPARED = "prepared"
SEND_METHOD_VOICE = "voice"
SEND_KIND_TEXT = "text"

# ---------------------------------------------------------------------------
# Timeouts / cooldowns used by reservation reclaim and scheduler retries
# ---------------------------------------------------------------------------

SCHEDULER_RETRY_COOLDOWN_MINUTES = 2
SCHEDULER_STALE_RUNNING_MINUTES = 15
CARD_RESERVATION_TIMEOUT_MINUTES = 15

# ---------------------------------------------------------------------------
# error_type values written to bot_user_cards on failed delivery
# ---------------------------------------------------------------------------

ERROR_TYPE_STALE_RESERVATION = "stale_reservation"
ERROR_TYPE_BOT_BLOCKED = "bot_blocked"
ERROR_TYPE_TEMPLATE_ERROR = "template_error"
ERROR_TYPE_TELEGRAM_TIMEOUT = "telegram_timeout"
ERROR_TYPE_AUDIO_UNAVAILABLE = "audio_unavailable"
ERROR_TYPE_TELEGRAM_ERROR = "telegram_error"
ERROR_TYPE_TECHNICAL = "technical_error"

# ---------------------------------------------------------------------------
# Truncation limits for error fields stored in the database
# ---------------------------------------------------------------------------

ERROR_TYPE_MAX_LEN = 100
ERROR_MESSAGE_MAX_LEN = 2000

# ---------------------------------------------------------------------------
# Telegram API / card template limits
# ---------------------------------------------------------------------------

TELEGRAM_MESSAGE_MAX_LEN = 4096

# ---------------------------------------------------------------------------
# Schedule and delivery (not env-configurable; change here, not in .env)
# ---------------------------------------------------------------------------

# Local wall-clock send slots (HH:MM). Cards/day == len(SEND_TIMES).
SEND_TIMES = ("13:00", "20:00")
TIMEZONE = "Europe/Moscow"  # UTC+3
SCHEDULE_GRACE_MINUTES = 60
SCHEDULER_POLL_SECONDS = 20
DELIVERY_CONCURRENCY = 5

# ---------------------------------------------------------------------------
# Database connection settings
# ---------------------------------------------------------------------------

DATABASE_POOL_SIZE = 5
DATABASE_CONNECT_TIMEOUT_SECONDS = 10
# Recycle pooled connections before Postgres/NAT idle timeouts (seconds).
DATABASE_POOL_RECYCLE_SECONDS = 1800

# ---------------------------------------------------------------------------
# Admin stats windows for "new users" (today / week / month)
# ---------------------------------------------------------------------------

ADMIN_STATS_WEEK_DAYS = 7
ADMIN_STATS_MONTH_DAYS = 30
