"""Forced-join (mandatory channel membership) checks.

Fetches the configured channels from the backend and verifies the user's
membership in each via the Bot API. Statuses ``member``, ``administrator``
and ``creator`` count as joined.
"""

import logging
from typing import Any

from aiogram import Bot
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramAPIError

from bot.services import api_client

logger = logging.getLogger(__name__)

_JOINED_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
}


async def get_missing_channels(bot: Bot, user_id: int) -> list[dict[str, Any]] | None:
    """Return the channels ``user_id`` has not joined yet.

    Returns:
        []    -- user is a member of every required channel (or none configured)
        [...] -- channels the user still has to join
        None  -- the backend API is unreachable; callers decide the policy
                 (the download handler fails open so users are not locked out).
    """
    channels = await api_client.get_forced_channels()
    if channels is None:
        return None

    missing: list[dict[str, Any]] = []
    for channel in channels:
        username = (channel.get("username") or "").lstrip("@")
        chat_ref: int | str | None = channel.get("channel_id") or (
            f"@{username}" if username else None
        )
        if chat_ref is None:
            continue
        try:
            member = await bot.get_chat_member(chat_ref, user_id)
        except TelegramAPIError as exc:
            # NOTE: the bot may not be an admin of this channel (Telegram
            # requires it for get_chat_member on channels) or the channel
            # may be misconfigured; skip it instead of blocking every user.
            logger.warning(
                "Skipping forced-join check for %r: %s", chat_ref, exc
            )
            continue
        if member.status not in _JOINED_STATUSES:
            missing.append(channel)
    return missing
