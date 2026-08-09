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
    db_url: str = ""

    @classmethod
    def load(cls, environ: Mapping[str, str] | None = None) -> Secrets:
        source = os.environ if environ is None else environ
        return cls(
            telegram_bot_token=source.get("TELEGRAM_BOT_TOKEN", "").strip(),
            db_url=source.get("OALD_DATABASE_URL", "").strip(),
        )


secrets = Secrets.load()
