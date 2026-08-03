"""Application bootstrap for long-polling Telegram delivery."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeChat

from vocabulary_bot.admin import create_admin_router
from vocabulary_bot.card_template import CardTemplate
from vocabulary_bot.config import BotConfig
from vocabulary_bot.database import Database
from vocabulary_bot.delivery import CardDeliveryService
from vocabulary_bot.handlers import create_router
from vocabulary_bot.scheduler import CardScheduler


LOGGER = logging.getLogger("vocabulary.bot")

USER_COMMANDS = (
    BotCommand(command="start", description="Начать работу"),
    BotCommand(command="card", description="Получить новую карточку"),
    BotCommand(command="settings", description="Настройки"),
    BotCommand(command="pause", description="Приостановить рассылку"),
    BotCommand(command="resume", description="Продолжить рассылку"),
    BotCommand(command="help", description="Помощь"),
)

ADMIN_COMMANDS = (
    BotCommand(command="admin", description="Открыть админ-панель"),
    BotCommand(command="users", description="Статистика пользователей"),
    BotCommand(command="user", description="Пользователь по Telegram ID"),
    BotCommand(command="word", description="Карточка слова"),
    BotCommand(command="send_test", description="Тестовая карточка"),
    BotCommand(command="reload_templates", description="Перезагрузить шаблоны"),
)


async def configure_commands(bot: Bot, config: BotConfig) -> None:
    await bot.set_my_commands(list(USER_COMMANDS))
    for admin_id in config.admin_ids:
        try:
            await bot.set_my_commands(
                [*USER_COMMANDS, *ADMIN_COMMANDS],
                scope=BotCommandScopeChat(chat_id=admin_id),
            )
        except Exception:  # noqa: BLE001
            LOGGER.warning(
                "Could not configure admin command scope for %s",
                admin_id,
                exc_info=True,
            )


async def run_bot(config: BotConfig) -> None:
    template = CardTemplate(config.card_template_path)
    both_template = CardTemplate(config.both_card_template_path)
    database = Database(
        config.database_url,
        pool_size=config.database_pool_size,
    )
    await database.open()
    delivery = CardDeliveryService(database, template, both_template)
    scheduler = CardScheduler(
        database=database,
        delivery=delivery,
        config=config,
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(
        create_router(
            database=database,
            delivery=delivery,
            config=config,
        )
    )
    dispatcher.include_router(
        create_admin_router(
            database=database,
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
        await configure_commands(bot, config)
        scheduler_task = asyncio.create_task(
            scheduler.run(bot),
            name="vocabulary-card-scheduler",
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
        await database.close()
