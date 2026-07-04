"""Download worker: consume the Redis-Streams queue -> download via
ProviderManager (with provider fallback) -> upload to the Telegram chat ->
consume quota AFTER the upload succeeded -> bookkeeping on download_requests.

Also runs periodic housekeeping:
- fails download requests dead-lettered by the queue so their quota releases,
- re-verifies pending payments whose gateway callback never completed,
- refreshes the panel-editable text cache and purges expired revoked tokens.

Run with: python -m app.workers.runner
"""
import asyncio
import datetime as dt
import logging
import os
import shutil
import tempfile

from sqlalchemy import and_, or_, select

from app.config import get_settings
from app.database import SessionLocal, utcnow
from app.models import Ad, DownloadRequest, Payment, User
from app.providers.base import DownloadError, DownloadResult, ProviderException
from app.providers.manager import manager
from app.services import texts_service
from app.services.ads_service import get_random_ad
from app.services.auth_service import purge_expired
from app.services.payment_service import verify_and_activate
from app.services.subscription_service import consume_download
from app.workers.queue import ack_and_remove, ensure_group, read_new, reclaim_stale

log = logging.getLogger("zed.worker")

HOUSEKEEPING_INTERVAL_SECONDS = 300
# Only reconcile payments old enough that the gateway's payment window has
# passed (avoid failing payments still in progress) and young enough to
# still be meaningful.
RECONCILE_MIN_AGE = dt.timedelta(minutes=30)
RECONCILE_MAX_AGE = dt.timedelta(hours=24)


def error_text(lang: str, code: str) -> str:
    """User-facing message for a DownloadError, via the panel-editable text
    cache (falls back to shipped defaults)."""
    return texts_service.text(lang, f"error.{code}")


async def _send_text(bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id, text)
    except Exception as exc:  # user blocked the bot, chat gone, etc.
        log.warning("could not message chat %s: %s", chat_id, exc)


async def _send_ad(bot, chat_id: int) -> None:
    """Deliver one random weighted active ad. Best-effort — an ad failure must
    never affect the download the user actually asked for."""
    settings = get_settings()
    if not settings.ADS_ENABLED:
        return
    try:
        async with SessionLocal() as session:
            ad = await get_random_ad(session)
        if ad is None:
            return
        if ad.media_url:
            await bot.send_photo(chat_id, ad.media_url, caption=ad.content)
        else:
            await bot.send_message(chat_id, ad.content)
    except Exception as exc:
        log.warning("could not send ad to chat %s: %s", chat_id, exc)


def _ad_before() -> bool:
    return get_settings().ADS_PLACEMENT in ("before", "both")


def _ad_after() -> bool:
    return get_settings().ADS_PLACEMENT in ("after", "both")


async def _upload(bot, chat_id: int, result: DownloadResult) -> str | None:
    """Send the media to the chat; returns the telegram file_id when available."""
    from aiogram.types import FSInputFile  # lazy: aiogram only needed at runtime

    settings = get_settings()
    caption_parts = []
    if result.title:
        caption_parts.append(result.title[:200])
    if settings.BOT_USERNAME:
        caption_parts.append(f"🤖 @{settings.BOT_USERNAME}")
    caption = "\n\n".join(caption_parts) or None

    media = FSInputFile(result.file_path, filename=result.file_name)
    if result.file_type == "video":
        msg = await bot.send_video(
            chat_id,
            media,
            caption=caption,
            duration=int(result.duration) if result.duration else None,
            width=result.width,
            height=result.height,
            supports_streaming=True,
        )
        return msg.video.file_id if msg.video else None
    if result.file_type == "audio":
        msg = await bot.send_audio(
            chat_id, media, caption=caption,
            duration=int(result.duration) if result.duration else None,
        )
        return msg.audio.file_id if msg.audio else None
    if result.file_type == "photo":
        msg = await bot.send_photo(chat_id, media, caption=caption)
        return msg.photo[-1].file_id if msg.photo else None
    msg = await bot.send_document(chat_id, media, caption=caption)
    return msg.document.file_id if msg.document else None


async def _fail(session, request: DownloadRequest, code: str) -> None:
    request.status = "failed"
    request.error_code = code
    request.completed_at = utcnow()
    await session.commit()


def _cleanup_when_done(task: asyncio.Task, dest_dir: str) -> None:
    """A timed-out provider call keeps running in its thread (yt-dlp cannot
    be force-stopped in-process; NOTE: v2 = subprocess isolation for a hard
    abort). Defer directory removal until it actually finishes — deleting
    files that are still being written would corrupt nothing durable but
    leak partial data and confuse the provider."""

    def _done(finished: asyncio.Task) -> None:
        try:
            exc = finished.exception()
            log.info("late download for %s finished (%s)", dest_dir, exc or "discarding result")
        except asyncio.CancelledError:
            pass
        shutil.rmtree(dest_dir, ignore_errors=True)

    task.add_done_callback(_done)


async def process_job(bot, payload: dict) -> None:
    settings = get_settings()
    request_id = payload.get("request_id")
    chat_id = payload.get("chat_id") or payload.get("telegram_id")
    lang = payload.get("language") or "fa"

    async with SessionLocal() as session:
        request = await session.get(DownloadRequest, request_id)
        if request is None:
            log.info("skipping job %s (row missing)", request_id)
            return
        # "queued" = fresh; "processing" = reclaimed after a worker crash.
        # Terminal states (completed/failed/denied) are duplicate deliveries —
        # skip so we never re-send a file the user already received.
        if request.status not in ("queued", "processing"):
            log.info("skipping job %s (status=%s, already handled)", request_id, request.status)
            return

        request.status = "processing"
        request.started_at = utcnow()
        await session.commit()

        dest_dir: str | None = None
        cleanup_now = True
        try:
            os.makedirs(settings.TEMP_DIR, exist_ok=True)
            dest_dir = tempfile.mkdtemp(prefix=f"req{request.id}-", dir=settings.TEMP_DIR)

            async def _run_download():
                # Own session: the job session must stay usable for failure
                # bookkeeping even if this task outlives the timeout below.
                async with SessionLocal() as dl_session:
                    return await manager.download(
                        dl_session, request.url, request.platform_id, dest_dir
                    )

            download_task = asyncio.create_task(_run_download())
            try:
                provider_row, result = await asyncio.wait_for(
                    asyncio.shield(download_task), timeout=settings.DOWNLOAD_TIMEOUT_SECONDS
                )
            except (TimeoutError, asyncio.TimeoutError):
                cleanup_now = False
                _cleanup_when_done(download_task, dest_dir)
                await _fail(session, request, DownloadError.PROVIDER_DOWN.value)
                await _send_text(bot, chat_id, error_text(lang, "provider_down"))
                return
            except ProviderException as exc:
                await _fail(session, request, exc.code.value)
                await _send_text(bot, chat_id, error_text(lang, exc.code.value))
                return

            if _ad_before():
                await _send_ad(bot, chat_id)

            try:
                telegram_file_id = await _upload(bot, chat_id, result)
            except Exception as exc:
                # Upload failed -> quota is NOT consumed (invariant #4).
                lowered = str(exc).lower()
                code = (
                    DownloadError.FILE_TOO_LARGE.value
                    if "too large" in lowered or "413" in lowered or "too big" in lowered
                    else "upload_failed"
                )
                log.warning("upload failed for request %s: %s", request.id, exc)
                await _fail(session, request, code)
                await _send_text(bot, chat_id, error_text(lang, code))
                return

            # Success: consume quota strictly AFTER the user received the file
            # (money-safety invariant #4), in the same transaction as the
            # request bookkeeping.
            await consume_download(session, request)
            request.status = "completed"
            request.provider_id = provider_row.id
            request.file_name = result.file_name
            request.file_size = result.file_size
            request.file_type = result.file_type
            request.telegram_file_id = telegram_file_id
            request.error_code = None
            request.completed_at = utcnow()
            await session.commit()
            log.info("request %s completed via provider %s", request.id, provider_row.slug)
            if _ad_after():
                await _send_ad(bot, chat_id)
        except Exception:
            # Anything unexpected (DB hiccup, provider bug) must not leave the
            # row stuck in "processing" — a stuck row silently occupies quota.
            log.exception("unexpected error processing request %s", request_id)
            await session.rollback()
            try:
                request = await session.get(DownloadRequest, request_id)
                if request is not None and request.status == "processing":
                    await _fail(session, request, DownloadError.UNKNOWN_ERROR.value)
            except Exception:
                log.exception("could not mark request %s failed", request_id)
            await _send_text(bot, chat_id, error_text(lang, "unknown_error"))
        finally:
            if cleanup_now and dest_dir:
                shutil.rmtree(dest_dir, ignore_errors=True)


# --- Housekeeping ------------------------------------------------------------


async def sweep_stale_requests() -> None:
    """Fail requests orphaned by a worker crash/restart so they stop
    occupying quota and history. Runs at startup and periodically."""
    settings = get_settings()
    now = utcnow()
    stale_processing_before = now - dt.timedelta(seconds=settings.DOWNLOAD_TIMEOUT_SECONDS * 2)
    stale_queued_before = now - dt.timedelta(hours=6)
    async with SessionLocal() as session:
        result = await session.execute(
            select(DownloadRequest).where(
                or_(
                    and_(
                        DownloadRequest.status == "processing",
                        DownloadRequest.started_at < stale_processing_before,
                    ),
                    and_(
                        DownloadRequest.status == "queued",
                        DownloadRequest.created_at < stale_queued_before,
                    ),
                )
            )
        )
        rows = list(result.scalars())
        for row in rows:
            row.status = "failed"
            row.error_code = DownloadError.UNKNOWN_ERROR.value
            row.completed_at = now
        if rows:
            await session.commit()
            # NOTE: no user notification here — too late to be useful.
            log.warning("swept %d stale download request(s)", len(rows))


async def reconcile_pending_payments(bot) -> None:
    """Re-verify pending payments whose callback never completed (this is
    what makes the callback page's 'verification will be retried' true).
    verify_and_activate is idempotent and race-safe, so overlapping with a
    late user-initiated callback is harmless."""
    now = utcnow()
    async with SessionLocal() as session:
        result = await session.execute(
            select(Payment.id, Payment.authority, Payment.user_id)
            .where(
                Payment.status == "pending",
                Payment.authority.is_not(None),
                Payment.created_at < now - RECONCILE_MIN_AGE,
                Payment.created_at > now - RECONCILE_MAX_AGE,
            )
            .limit(50)
        )
        candidates = result.all()

    for payment_id, authority, user_id in candidates:
        async with SessionLocal() as session:
            outcome = await verify_and_activate(session, authority=authority)
            if outcome.status != "success":
                continue
            log.info("reconciled payment %s (ref %s)", payment_id, outcome.ref_id)
            user = await session.get(User, user_id)
        if user is not None:
            await _send_text(bot, user.telegram_id, texts_service.text(user.language, "payment.confirmed"))


async def purge_revoked_tokens() -> None:
    """Delete admin-token blacklist rows whose tokens have expired anyway."""
    async with SessionLocal() as session:
        removed = await purge_expired(session)
        if removed:
            await session.commit()
            log.info("purged %d expired revoked-token row(s)", removed)


async def refresh_texts() -> None:
    async with SessionLocal() as session:
        await texts_service.refresh(session)


async def housekeeping_loop(bot) -> None:
    while True:
        try:
            # Fail rows dead-lettered by the queue (their stream entry is gone
            # but the row is still "processing") so quota is released.
            await sweep_stale_requests()
            await reconcile_pending_payments(bot)
            await purge_revoked_tokens()
            await refresh_texts()
        except Exception:
            log.exception("housekeeping error")
        await asyncio.sleep(HOUSEKEEPING_INTERVAL_SECONDS)


# --- Entry point -----------------------------------------------------------------


def _build_bot():
    """Bot pointed at TELEGRAM_API_URL when configured (self-hosted
    telegram-bot-api lifts the ~50 MB upload cap); official API otherwise."""
    from aiogram import Bot  # lazy: keeps module importable without aiogram

    settings = get_settings()
    if settings.TELEGRAM_API_URL:
        from aiogram.client.session.aiohttp import AiohttpSession
        from aiogram.client.telegram import TelegramAPIServer

        server = TelegramAPIServer.from_base(settings.TELEGRAM_API_URL.rstrip("/"))
        return Bot(token=settings.BOT_TOKEN, session=AiohttpSession(api=server))
    return Bot(token=settings.BOT_TOKEN)


async def _handle(bot, entry_id: str, payload: dict) -> None:
    """Process one job and ack it. If process_job raises unexpectedly we do
    NOT ack, so the entry stays pending and is reclaimed/retried (and
    eventually dead-lettered) rather than silently lost."""
    try:
        await process_job(bot, payload)
    except Exception:
        log.exception("unhandled error processing entry %s (%s) — leaving unacked", entry_id, payload)
        return
    await ack_and_remove(entry_id)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    settings = get_settings()
    os.makedirs(settings.TEMP_DIR, exist_ok=True)

    consumer = f"worker-{os.getpid()}"
    await ensure_group()
    await refresh_texts()  # warm the panel-editable text cache before serving
    bot = _build_bot()
    housekeeper = asyncio.create_task(housekeeping_loop(bot))
    log.info("worker %s started, waiting for jobs on the stream", consumer)
    try:
        while True:
            try:
                # First retry anything a dead worker left pending, then take
                # fresh work (blocking briefly so the loop is not a busy-wait).
                reclaimed = await reclaim_stale(
                    consumer, settings.QUEUE_MAX_DELIVERIES, settings.QUEUE_RECLAIM_IDLE_MS
                )
                for entry_id, payload in reclaimed:
                    log.info("reclaimed stale job %s", entry_id)
                    await _handle(bot, entry_id, payload)

                entries = await read_new(consumer, count=1, block_ms=5000)
            except Exception as exc:  # redis hiccup — back off and retry
                log.error("queue error: %s", exc)
                await asyncio.sleep(3)
                continue
            for entry_id, payload in entries:
                await _handle(bot, entry_id, payload)
    finally:
        housekeeper.cancel()


if __name__ == "__main__":
    asyncio.run(main())
