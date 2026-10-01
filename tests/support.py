"""Shared test helpers."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

from tgbot.db.sync import destroy_database, ensure_database_exists

TEST_OALD_DATABASE_URL = os.environ.get("TEST_OALD_DATABASE_URL", "")

requires_oald_database = pytest.mark.skipif(
    not TEST_OALD_DATABASE_URL,
    reason="TEST_OALD_DATABASE_URL is not set",
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@contextmanager
def temporary_migrated_database(
    base_url: str | None = None,
    *,
    prefix: str = "vocab_oald_",
) -> Iterator[str]:
    """Create a throwaway DB, upgrade to Alembic head, then drop it."""
    source_url = base_url or TEST_OALD_DATABASE_URL
    if not source_url:
        raise RuntimeError("TEST_OALD_DATABASE_URL is not set")

    db_name = f"{prefix}{uuid.uuid4().hex}"
    db_url = (
        make_url(source_url).set(database=db_name).render_as_string(hide_password=False)
    )

    ensure_database_exists(db_url)
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    with patch.dict(os.environ, {"OALD_DATABASE_URL": db_url}):
        import tgbot.secrets as app_secrets

        app_secrets.secrets = app_secrets.Secrets.load()
        command.upgrade(config, "head")

    try:
        yield db_url
    finally:
        destroy_database(db_url)
