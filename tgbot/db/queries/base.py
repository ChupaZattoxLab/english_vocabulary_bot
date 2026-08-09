"""Shared base for query helpers that require an async SQLAlchemy engine."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine


class EngineBound:
    """Declares the engine attribute that Database provides at runtime."""

    engine: AsyncEngine
