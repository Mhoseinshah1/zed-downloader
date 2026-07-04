"""Reliable job queue on Redis Streams (replaces the earlier BLPOP list).

Why Streams: BLPOP is at-most-once — a worker that dies mid-job loses it.
Streams give us a consumer group with a Pending Entries List (PEL): a message
stays pending until explicitly XACK'd, so a crashed worker's job can be
reclaimed (XAUTOCLAIM) by another worker and retried, and repeatedly-failing
jobs are moved to a dead-letter stream instead of looping forever.

Lifecycle of one job id:
  enqueue        -> XADD to STREAM_KEY
  worker picks   -> XREADGROUP ">" (new) or XAUTOCLAIM (reclaimed)
  success/terminal failure -> ack_and_remove: XACK + XDEL
  worker crash   -> stays in PEL, reclaimed after QUEUE_RECLAIM_IDLE_MS
  too many tries -> dead_letter: XADD to DEAD_KEY, then XACK + XDEL

Still deliberately transparent (plain Redis commands, no Celery) so the whole
pipeline is auditable.
"""
import json

import redis.asyncio as redis

from app.config import get_settings

STREAM_KEY = "zed:download:stream"
DEAD_KEY = "zed:download:dead"
GROUP = "zed:workers"

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(get_settings().REDIS_URL, decode_responses=True)
    return _client


async def ensure_group() -> None:
    """Create the consumer group (and the stream) if absent. Idempotent."""
    r = get_redis()
    try:
        await r.xgroup_create(STREAM_KEY, GROUP, id="0", mkstream=True)
    except redis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):  # already exists — fine
            raise


async def enqueue(payload: dict) -> str:
    """Append a job; returns the stream entry id."""
    return await get_redis().xadd(STREAM_KEY, {"data": json.dumps(payload)})


def _parse(entry) -> tuple[str, dict]:
    entry_id, fields = entry
    return entry_id, json.loads(fields["data"])


async def read_new(consumer: str, count: int = 1, block_ms: int = 5000) -> list[tuple[str, dict]]:
    """Fetch never-before-delivered entries for this consumer."""
    r = get_redis()
    resp = await r.xreadgroup(GROUP, consumer, {STREAM_KEY: ">"}, count=count, block=block_ms)
    if not resp:
        return []
    _stream, entries = resp[0]
    return [_parse(e) for e in entries]


async def reclaim_stale(consumer: str, max_deliveries: int, idle_ms: int, count: int = 10) -> list[tuple[str, dict]]:
    """Claim entries left pending by a dead worker (idle > idle_ms).

    Entries whose delivery count already exceeds max_deliveries are moved to
    the dead-letter stream and acked instead of being returned for retry.
    """
    r = get_redis()
    try:
        result = await r.xautoclaim(
            STREAM_KEY, GROUP, consumer, min_idle_time=idle_ms, start_id="0-0", count=count
        )
    except redis.ResponseError:
        return []
    # redis-py returns (next_cursor, claimed_messages) or (next, claimed, deleted).
    claimed = result[1] if len(result) >= 2 else []

    ready: list[tuple[str, dict]] = []
    for entry in claimed:
        if entry is None or entry[1] is None:  # entry was deleted from the stream
            continue
        entry_id, payload = _parse(entry)
        deliveries = await _delivery_count(entry_id)
        if deliveries > max_deliveries:
            await dead_letter(entry_id, payload, reason=f"exceeded {max_deliveries} deliveries")
        else:
            ready.append((entry_id, payload))
    return ready


async def _delivery_count(entry_id: str) -> int:
    r = get_redis()
    pending = await r.xpending_range(STREAM_KEY, GROUP, min=entry_id, max=entry_id, count=1)
    if not pending:
        return 0
    return int(pending[0]["times_delivered"])


async def ack_and_remove(entry_id: str) -> None:
    """Job is finished (success or terminal failure): ack + delete so the
    stream length reflects only outstanding work."""
    r = get_redis()
    await r.xack(STREAM_KEY, GROUP, entry_id)
    await r.xdel(STREAM_KEY, entry_id)


async def dead_letter(entry_id: str, payload: dict, reason: str) -> None:
    r = get_redis()
    await r.xadd(DEAD_KEY, {"data": json.dumps(payload), "reason": reason, "orig_id": entry_id})
    await ack_and_remove(entry_id)


async def queue_length() -> int:
    """Outstanding jobs (undelivered + in-flight). Because finished jobs are
    XDEL'd, XLEN is the live backlog."""
    return int(await get_redis().xlen(STREAM_KEY))
