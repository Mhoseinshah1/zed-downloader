"""URL intake (Phase 2).

The bot detects a public link, records it via the placeholder intake endpoint,
and replies that downloading arrives in the next phase. No real download is
triggered here. Non-URL text gets a friendly "send a valid link" reply.
Legal boundary: public/permitted links only — no login/cookies/private access.
"""

import logging
import re
import time
from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import Message

from bot.i18n import t
from bot.services import api_client

logger = logging.getLogger(__name__)

router = Router(name="download")

_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)

# Slug -> display label for the detected platform.
_PLATFORM_DISPLAY = {
    "instagram": "Instagram",
    "youtube": "YouTube",
    "tiktok": "TikTok",
    "twitter": "X / Twitter",
    "generic": "Generic",
    "unknown": "?",
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


def is_valid_url(text: str | None) -> bool:
    """True when the text contains an http(s) URL."""
    return extract_url(text) is not None


def detect_platform(url: str | None) -> str | None:
    """Detect the platform from a URL by host. Returns a slug, 'generic' for
    any other http(s) URL, or None when there is no URL. Host-based matching
    avoids false positives (e.g. 'box.com' is not treated as x.com)."""
    found = extract_url(url)
    if found is None:
        return None
    host = (urlparse(found).hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]

    def match(*domains: str) -> bool:
        return any(host == d or host.endswith("." + d) for d in domains)

    if match("instagram.com", "instagr.am"):
        return "instagram"
    if match("youtube.com", "youtu.be"):
        return "youtube"
    if match("tiktok.com"):
        return "tiktok"
    if match("x.com", "twitter.com"):
        return "twitter"
    return "generic"


def platform_display(slug: str | None) -> str:
    return _PLATFORM_DISPLAY.get(slug or "unknown", slug or "?")


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


async def _record_placeholder(message: Message, lang: str, url: str, chat_id: int | None) -> None:
    """Record the link via the placeholder endpoint and acknowledge."""
    logger.info("URL received: user=%s chat_id=%s", message.from_user.id, chat_id)
    result = await api_client.create_download_request(
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

    slug = result.get("detected_platform") or detect_platform(url) or "unknown"
    logger.info("platform detected: %s (request_id=%s)", slug, result.get("request_id"))
    await message.reply(t(lang, "download.placeholder", platform=platform_display(slug)))


@router.message(F.chat.type == ChatType.PRIVATE, F.text)
async def private_message(message: Message, lang: str) -> None:
    if message.text.startswith("/"):
        # Unknown command; command handlers run in earlier routers.
        return

    if not is_valid_url(message.text):
        logger.info("invalid input from user=%s", message.from_user.id)
        await message.answer(t(lang, "download.invalid_url"))
        return

    await _record_placeholder(message, lang, extract_url(message.text), chat_id=None)


@router.message(F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}), F.text)
async def group_message(message: Message, lang: str) -> None:
    url = extract_url(message.text)
    if url is None:
        # Stay silent in groups unless a URL is posted.
        return
    await _ensure_group_registered(message)
    await _record_placeholder(message, lang, url, chat_id=message.chat.id)
