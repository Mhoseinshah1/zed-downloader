"""Download flow: URL messages in private chats and groups.

The bot only acknowledges here (queued / denied / buy prompt). The backend
worker delivers the actual media file and per-error messages to the chat.
"""

import logging
import re
import time
from typing import Any

from aiogram import Bot, F, Router
from aiogram.enums import ChatType
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery, Message

from bot.i18n import t
from bot.keyboards.forced_join import VERIFY_CALLBACK, forced_join_keyboard
from bot.keyboards.plans import plans_keyboard
from bot.services import api_client
from bot.services.forced_join import get_missing_channels

logger = logging.getLogger(__name__)

router = Router(name="download")

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

_KNOWN_DENIED_REASONS = {
    "blocked",
    "maintenance",
    "limit_reached",
    "need_subscription",
    "group_disabled",
}

# telegram_chat_id -> monotonic expiry; avoids re-upserting a group on every URL
_group_upsert_cache: dict[int, float] = {}
_GROUP_UPSERT_TTL = 300.0


def extract_url(text: str | None) -> str | None:
    """Return the first http(s) URL found in the text, if any."""
    if not text:
        return None
    match = _URL_RE.search(text)
    return match.group(0) if match else None


async def _ensure_group_registered(message: Message) -> None:
    """Upsert the group via the API, throttled with an in-memory TTL cache."""
    now = time.monotonic()
    if _group_upsert_cache.get(message.chat.id, 0.0) > now:
        return
    result = await api_client.upsert_group(
        telegram_chat_id=message.chat.id,
        title=message.chat.title,
        username=message.chat.username,
    )
    if result is not None:
        _group_upsert_cache[message.chat.id] = now + _GROUP_UPSERT_TTL


async def _process_download(
    message: Message, lang: str, url: str, chat_id: int | None
) -> None:
    """Send the request to the backend and reply according to its status."""
    result = await api_client.request_download(
        telegram_id=message.from_user.id,
        url=url,
        chat_id=chat_id,
        username=message.from_user.username,
        first_name=message.from_user.first_name,
        last_name=message.from_user.last_name,
        language=lang,
    )
    if result is None:
        await message.reply(t(lang, "errors.api_unreachable"))
        return

    status = result.get("status")
    if status == "queued":
        await message.reply(
            t(lang, "download.queued", request_id=result.get("request_id", "-"))
        )
        return

    if status == "denied":
        reason = result.get("reason", "")
        key = (
            f"download.denied.{reason}"
            if reason in _KNOWN_DENIED_REASONS
            else "download.denied.generic"
        )
        reply_markup = None
        if reason == "need_subscription":
            plans = result.get("plans") or await api_client.get_plans() or []
            if plans:
                reply_markup = plans_keyboard(plans, lang)
        await message.reply(t(lang, key), reply_markup=reply_markup)
        return

    if status == "error":
        # Only reason in the contract is "unsupported_url".
        await message.reply(t(lang, "download.unsupported_url"))
        return

    logger.warning("Unexpected download/request response: %r", result)
    await message.reply(t(lang, "download.denied.generic"))


@router.message(F.chat.type == ChatType.PRIVATE, F.text)
async def private_message(message: Message, bot: Bot, lang: str) -> None:
    if message.text.startswith("/"):
        # Unknown command; command handlers run in earlier routers.
        return

    url = extract_url(message.text)
    if url is None:
        await message.answer(t(lang, "download.invalid_url"))
        return

    # Forced-join check applies to private chats only.
    missing = await get_missing_channels(bot, message.from_user.id)
    if missing:
        await message.answer(
            t(lang, "forced_join.prompt"),
            reply_markup=forced_join_keyboard(missing, lang),
        )
        return
    # NOTE: missing is None when the API is unreachable -- fail open and let
    # the download request itself surface any error to the user.

    await _process_download(message, lang, url, chat_id=None)


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), F.text)
async def group_message(message: Message, lang: str) -> None:
    url = extract_url(message.text)
    if url is None:
        # Stay silent in groups unless a URL is posted.
        return

    await _ensure_group_registered(message)
    # NOTE: forced-join check is intentionally skipped in groups for UX;
    # the backend still enforces per-user limits and group enablement.
    await _process_download(message, lang, url, chat_id=message.chat.id)


@router.callback_query(F.data == VERIFY_CALLBACK)
async def verify_forced_join(callback: CallbackQuery, bot: Bot, lang: str) -> None:
    missing = await get_missing_channels(bot, callback.from_user.id)
    if missing is None:
        await callback.answer(t(lang, "errors.api_unreachable"), show_alert=True)
        return
    if missing:
        await callback.answer(t(lang, "forced_join.still_missing"), show_alert=True)
        return

    await callback.answer()
    confirmation = t(lang, "forced_join.verified")
    try:
        await callback.message.edit_text(confirmation)
    except TelegramAPIError:
        await callback.message.answer(confirmation)
