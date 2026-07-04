"""User middleware: upsert the user via the internal API and resolve language.

The middleware runs for messages and callback queries. To avoid hitting the
API on every single update it caches the resolved language per user for a
short TTL in memory. The resolved language is stashed into handler data as
``data["lang"]`` so every handler can accept a ``lang: str`` argument.
"""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User

from bot.i18n import DEFAULT_LANGUAGE, PRIMARY_LANGUAGE
from bot.services import api_client

logger = logging.getLogger(__name__)

_TTL_SECONDS = 60.0
_MAX_CACHE_SIZE = 10_000

# user_id -> (expires_at_monotonic, language)
_cache: dict[int, tuple[float, str]] = {}


def set_cached_language(user_id: int, language: str) -> None:
    """Update the cached language immediately (used after /lang changes)."""
    _cache[user_id] = (time.monotonic() + _TTL_SECONDS, language)


def _prune_cache(now: float) -> None:
    if len(_cache) <= _MAX_CACHE_SIZE:
        return
    for user_id in [uid for uid, (expires, _) in _cache.items() if expires <= now]:
        _cache.pop(user_id, None)


def _fallback_language(from_user: User) -> str:
    """Best-effort language when the API is unreachable."""
    code = (from_user.language_code or "").lower()
    return PRIMARY_LANGUAGE if code.startswith(PRIMARY_LANGUAGE) else DEFAULT_LANGUAGE


class UserMiddleware(BaseMiddleware):
    """Upserts the sender via the internal API and injects ``data['lang']``."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user: User | None = getattr(event, "from_user", None)
        if from_user is None or from_user.is_bot:
            data["lang"] = DEFAULT_LANGUAGE
            return await handler(event, data)

        now = time.monotonic()
        cached = _cache.get(from_user.id)
        if cached is not None and cached[0] > now:
            lang = cached[1]
        else:
            # NOTE: language_code is only a hint on upsert; the backend keeps
            # the user's explicitly chosen language and the response value is
            # authoritative here.
            user = await api_client.upsert_user(
                telegram_id=from_user.id,
                username=from_user.username,
                first_name=from_user.first_name,
                last_name=from_user.last_name,
                language=(from_user.language_code or "").split("-")[0].lower() or None,
            )
            if user is None:
                # API unreachable: fall back to the Telegram client language
                # and do NOT cache, so the next update retries the upsert.
                lang = _fallback_language(from_user)
            else:
                lang = user.get("language") or _fallback_language(from_user)
                _prune_cache(now)
                _cache[from_user.id] = (now + _TTL_SECONDS, lang)
                logger.info("user upserted: telegram_id=%s lang=%s", from_user.id, lang)

        data["lang"] = lang
        return await handler(event, data)
