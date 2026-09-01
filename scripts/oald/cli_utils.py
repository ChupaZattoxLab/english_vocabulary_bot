"""Shared CLI helpers for OALD / Oxford build scripts."""

from __future__ import annotations

import argparse
import logging
import os

from tgbot.secrets import Secrets

LOG_LEVELS = ("DEBUG", "INFO", "WARNING", "ERROR")


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def nonnegative_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def nonnegative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def resolve_db_url(cli_value: str | None = None) -> str | None:
    """Resolve DB URL: CLI, then ``OALD_DATABASE_URL``, then ``DATABASE_URL``."""
    if cli_value:
        return cli_value
    secrets = Secrets.load()
    if secrets.db_url:
        return secrets.db_url
    # One-release fallback for scripts that previously used DATABASE_URL only.
    fallback = os.environ.get("DATABASE_URL", "").strip()
    return fallback or None


def resolve_admin_db_url(cli_value: str | None = None) -> str | None:
    """Optional admin URL used only to create a missing target database."""
    if cli_value:
        return cli_value
    value = os.environ.get("OALD_ADMIN_DATABASE_URL", "").strip()
    return value or None
