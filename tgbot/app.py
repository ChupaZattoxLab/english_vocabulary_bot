"""Application bootstrap for long-polling Telegram delivery."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeChat

from tgbot.bot_config import BotConfig
from tgbot.db import Database
from tgbot.delivery import CardDeliveryService
from tgbot.delivery.scheduler import CardScheduler
from tgbot.handlers import create_admin_router, create_router
from tgbot.localization import locale

LOGGER = logging.getLogger("tgbot")

USER_COMMANDS = (
    BotCommand(command="start", description=locale.commands.start),
    BotCommand(command="card", description=locale.commands.card),
    BotCommand(command="settings", description=locale.commands.settings),
    BotCommand(command="pause", description=locale.commands.pause),
    BotCommand(command="resume", description=locale.commands.resume),
    BotCommand(command="help", description=locale.commands.help),
)

ADMIN_COMMANDS = (
    BotCommand(command="admin", description=locale.commands.admin),
    BotCommand(command="stats", description=locale.commands.stats),
    BotCommand(command="user", description=locale.commands.user),
    BotCommand(command="word", description=locale.commands.word),
)


async def run_bot(config: BotConfig) -> None:
    db = Database(
        config.db_url,
        pool_size=config.db_pool_size,
    )
    await db.open()

    delivery = CardDeliveryService(db)
    scheduler = CardScheduler(
        db=db,
        delivery=delivery,
        config=config,
    )

    dispatcher = Dispatcher()
    dispatcher.include_router(
        create_router(
            db=db,
            delivery=delivery,
            config=config,
        )
    )
    dispatcher.include_router(
        create_admin_router(
            db=db,
            delivery=delivery,
            config=config,
        )
    )

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    scheduler_task: asyncio.Task[None] | None = None
    try:
        await configure_commands(bot, db)

        scheduler_task = asyncio.create_task(
            scheduler.run(bot),
            name="tgbot-card-scheduler",
        )

        LOGGER.info("Starting Telegram long polling")
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
            close_bot_session=False,
        )

    finally:
        scheduler.stop()
        if scheduler_task:
            await scheduler_task

        await bot.session.close()
        await db.close()


async def configure_commands(bot: Bot, db: Database) -> None:
    await bot.set_my_commands(list(USER_COMMANDS))

    for admin_id in await db.get_admin_user_ids():
        await bot.set_my_commands(
            [*USER_COMMANDS, *ADMIN_COMMANDS],
            scope=BotCommandScopeChat(chat_id=admin_id),
        )
