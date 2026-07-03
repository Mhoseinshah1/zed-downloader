"""Transparent Redis-list job queue (deliberately not Celery, so the whole
pipeline stays auditable: RPUSH on enqueue, BLPOP on dequeue, that's it)."""
import json

import redis.asyncio as redis

from app.config import get_settings

QUEUE_KEY = "zed:download:queue"

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(get_settings().REDIS_URL, decode_responses=True)
    return _client


async def enqueue(payload: dict) -> None:
    await get_redis().rpush(QUEUE_KEY, json.dumps(payload))


async def dequeue(timeout: int = 5) -> dict | None:
    """Blocking pop; returns None when the timeout elapses with no job."""
    item = await get_redis().blpop(QUEUE_KEY, timeout=timeout)
    if item is None:
        return None
    _, raw = item
    return json.loads(raw)


async def queue_length() -> int:
    return int(await get_redis().llen(QUEUE_KEY))
