"""Delivery package types and constants (delivery/ only)."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
CARD_TEMPLATE_PATH = TEMPLATES_DIR / "card_template.html"
BOTH_CARD_TEMPLATE_PATH = TEMPLATES_DIR / "card_template_both.html"

TELEGRAM_MESSAGE_MAX_LEN = 4096

SEND_KIND_TEXT = "text"


class DeliveryStatus(StrEnum):
    DELIVERED = "delivered"
    FAILED = "failed"
    SKIPPED = "skipped"


# Values written to bot_user_cards.error_type on failed delivery.
ERROR_TYPE_BOT_BLOCKED = "bot_blocked"
ERROR_TYPE_TEMPLATE_ERROR = "template_error"
ERROR_TYPE_TELEGRAM_TIMEOUT = "telegram_timeout"
ERROR_TYPE_AUDIO_UNAVAILABLE = "audio_unavailable"
ERROR_TYPE_TELEGRAM_ERROR = "telegram_error"
ERROR_TYPE_TECHNICAL = "technical_error"
