"""Block user features until the sender belongs to the required channel."""

from __future__ import annotations

from typing import Any

from aiogram import Bot
from aiogram.dispatcher.event.bases import NextMiddlewareType
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from tgbot.channel_membership import TelegramMembership, telegram_membership
from tgbot.handlers.helpers import callback_message
from tgbot.handlers.keyboard import subscription_keyboard
from tgbot.localization import locale
from tgbot.types import REQUIRED_CHANNEL


async def gate_message(
    handler: NextMiddlewareType[Message],
    event: Message,
    data: dict[str, Any],
) -> Any:
    """Let a subscriber's message through and refuse everyone else."""
    membership = await membership_of(event, data)
    if membership is None or membership is TelegramMembership.MEMBER:
        return await handler(event, data)
    await deny_message(event, membership)
    return None


async def membership_of(
    event: Message | CallbackQuery,
    data: dict[str, Any],
) -> TelegramMembership | None:
    """Ask Telegram if the sender is a member, or skip when there is no sender."""
    user = event.from_user
    if user is None:
        return None
    bot: Bot = data["bot"]
    return await telegram_membership(bot, REQUIRED_CHANNEL, user.id)


async def deny_message(message: Message, membership: TelegramMembership) -> None:
    """Send the refusal as a chat message."""
    text, _, markup = subscription_prompt(membership)
    await message.answer(text, reply_markup=markup)


def subscription_prompt(
    membership: TelegramMembership,
) -> tuple[str, str, InlineKeyboardMarkup | None]:
    """Refusal text: no buttons on a failed check, otherwise the channel link."""
    if membership is TelegramMembership.UNKNOWN:
        text = locale.user.subscription_check_failed
        return text, text, None
    return (
        locale.user.need_subscription,
        locale.user.subscription_alert,
        subscription_keyboard(),
    )


async def gate_callback(
    handler: NextMiddlewareType[CallbackQuery],
    event: CallbackQuery,
    data: dict[str, Any],
) -> Any:
    """Let a subscriber's button press through and refuse everyone else."""
    membership = await membership_of(event, data)
    if membership is None or membership is TelegramMembership.MEMBER:
        return await handler(event, data)
    await deny_callback(event, membership)
    return None


async def deny_callback(
    callback: CallbackQuery, membership: TelegramMembership
) -> None:
    """Show the refusal as an alert and as the same chat message."""
    text, alert, markup = subscription_prompt(membership)
    await callback.answer(alert, show_alert=True)
    message = callback_message(callback)
    if message is not None:
        await message.answer(text, reply_markup=markup)
