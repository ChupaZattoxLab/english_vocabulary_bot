"""Telegram vocabulary bot package."""

from __future__ import annotations

import asyncio
import sys


# Psycopg's async implementation requires a selector-based loop on Windows.
if sys.platform == "win32" and hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
