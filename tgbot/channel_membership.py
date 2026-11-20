"""Whether a Telegram user belongs to the required channel."""

from __future__ import annotations

import logging
from enum import StrEnum

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ResultChatMemberUnion

LOGGER = logging.getLogger("tgbot.channel")


class TelegramMembership(StrEnum):
    MEMBER = "member"
    NOT_MEMBER = "not_member"
    UNKNOWN = "unknown"


async def telegram_membership(
    bot: Bot,
    channel: str,
    user_id: int,
) -> TelegramMembership:
    """Ask Telegram whether this user belongs to the channel."""
    try:
        member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
    except TelegramAPIError as exc:
        LOGGER.warning(
            "Channel membership check failed for user %s in %s: %s",
            user_id,
            channel,
            exc.message,
        )
        return TelegramMembership.UNKNOWN
    return membership_of(member)


def membership_of(member: ResultChatMemberUnion) -> TelegramMembership:
    """Map one getChatMember result to a gate decision."""
    if member.status in {ChatMemberStatus.LEFT, ChatMemberStatus.KICKED} or (
        member.status == ChatMemberStatus.RESTRICTED and not member.is_member
    ):
        return TelegramMembership.NOT_MEMBER
    return TelegramMembership.MEMBER
