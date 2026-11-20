"""Bot command registration."""

from __future__ import annotations

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SetMyCommands
from aiogram.types import BotCommandScopeChat

from tgbot.app import configure_commands


class _Database:
    async def get_admin_user_ids(self) -> list[int]:
        return [101, 202]


class _Bot:
    def __init__(self) -> None:
        self.scopes: list[int | None] = []

    async def set_my_commands(self, commands: object, scope: object = None) -> None:
        chat_id = scope.chat_id if isinstance(scope, BotCommandScopeChat) else None
        self.scopes.append(chat_id)
        if chat_id == 101:
            raise TelegramBadRequest(
                method=SetMyCommands(commands=[]),
                message="Bad Request: chat not found",
            )


async def test_unknown_admin_chat_does_not_stop_command_setup() -> None:
    bot = _Bot()

    await configure_commands(bot, _Database())  # type: ignore[arg-type]

    assert bot.scopes == [None, 101, 202]
