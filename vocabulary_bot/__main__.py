"""Run the Telegram vocabulary bot with ``python -m vocabulary_bot``."""

from __future__ import annotations

import asyncio
import logging

from vocabulary_bot.app import run_bot
from vocabulary_bot.config import BotConfig, ConfigError, PROJECT_ROOT, load_env_file


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    try:
        load_env_file(PROJECT_ROOT / ".env")
        config = BotConfig.from_env()
        asyncio.run(run_bot(config))
        return 0
    except ConfigError as exc:
        logging.getLogger("vocabulary.bot").error("Configuration error: %s", exc)
        return 2
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
