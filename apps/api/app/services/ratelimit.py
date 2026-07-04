"""Redis-backed fixed-window rate limiting for download requests.

Applied per identity (the telegram user, and separately the group chat) so a
single user cannot flood the queue and a busy group cannot starve everyone
else. Fails OPEN: if Redis is unavailable the limiter allows the request
rather than blocking all downloads (availability over strictness — the queue
and quota checks are the real safety nets).
"""
import logging

from app.config import get_settings
from app.workers.queue import get_redis

log = logging.getLogger("zed.ratelimit")


async def check_and_increment(scope: str, identity: int | str) -> bool:
    """Return True if the action is allowed, False if the limit is exceeded.

    Fixed window: one counter key per identity that expires after the window.
    """
    settings = get_settings()
    if not settings.RATE_LIMIT_ENABLED:
        return True

    key = f"zed:ratelimit:{scope}:{identity}"
    window = settings.RATE_LIMIT_WINDOW_SECONDS
    limit = settings.RATE_LIMIT_MAX_REQUESTS
    try:
        r = get_redis()
        # INCR then set the expiry only when the key is first created, so the
        # window is anchored to the first request in it.
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, window)
        return count <= limit
    except Exception as exc:  # Redis down — fail open.
        log.warning("rate limiter unavailable (%s); allowing request", exc)
        return True


async def is_rate_limited(*, telegram_id: int, chat_id: int | None) -> bool:
    """True if either the user or (when in a group) the chat is over budget."""
    if not await check_and_increment("user", telegram_id):
        return True
    if chat_id is not None and chat_id < 0:
        if not await check_and_increment("chat", chat_id):
            return True
    return False
