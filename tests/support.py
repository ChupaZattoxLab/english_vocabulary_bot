"""Shared test helpers."""

from __future__ import annotations

import os

import pytest

TEST_OALD_DATABASE_URL = os.environ.get("TEST_OALD_DATABASE_URL", "")

requires_oald_database = pytest.mark.skipif(
    not TEST_OALD_DATABASE_URL,
    reason="TEST_OALD_DATABASE_URL is not set",
)
