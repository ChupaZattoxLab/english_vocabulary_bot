"""Secrets loaded from process environment / ``.env``."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = Path(__file__).resolve().parent

load_dotenv(PROJECT_ROOT / ".env")


class ConfigError(ValueError):
    """Raised when bot configuration is missing or invalid."""


@dataclass(frozen=True)
class Secrets:
    telegram_bot_token: str = ""
    telegram_admin_ids: str = ""
    db_url: str = ""

    @classmethod
    def load(cls, environ: Mapping[str, str] | None = None) -> Secrets:
        source = os.environ if environ is None else environ
        return cls(
            telegram_bot_token=source.get("TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_admin_ids=source.get("TELEGRAM_ADMIN_IDS", "").strip(),
            db_url=source.get("OALD_DATABASE_URL", "").strip(),
        )

    @property
    def admin_ids(self) -> frozenset[int]:
        return parse_admin_ids(self.telegram_admin_ids)


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


secrets = Secrets.load()
