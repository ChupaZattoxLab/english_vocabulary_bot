"""Secrets loaded from process environment / ``.env`` via pydantic-settings."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Self

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = Path(__file__).resolve().parent

# Keep os.environ populated for tools that still read getenv directly.
load_dotenv(PROJECT_ROOT / ".env")


class ConfigError(ValueError):
    """Raised when bot configuration is missing or invalid."""


class Secrets(BaseSettings):
    """Env-backed secrets (same role as ravenspedia ``Settings``)."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        populate_by_name=True,
    )

    telegram_bot_token: str = Field(default="")
    db_url: str = Field(default="", validation_alias="OALD_DATABASE_URL")

    @field_validator("telegram_bot_token", "db_url", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @classmethod
    def load(cls, environ: Mapping[str, str] | None = None) -> Self:
        """Load from process env, or from an explicit mapping (tests)."""
        if environ is None:
            return cls()

        return cls(
            telegram_bot_token=environ.get("TELEGRAM_BOT_TOKEN", ""),
            db_url=environ.get("OALD_DATABASE_URL", ""),
        )


secrets = Secrets.load()
