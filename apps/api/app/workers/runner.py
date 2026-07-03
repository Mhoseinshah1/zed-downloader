"""Download worker: BLPOP the Redis queue -> download via ProviderManager
(with provider fallback) -> upload to the Telegram chat -> consume quota
AFTER the upload succeeded -> bookkeeping on download_requests.

Run with: python -m app.workers.runner
"""
import asyncio
import logging
import os
import shutil
import tempfile

from app.config import get_settings
from app.database import SessionLocal, utcnow
from app.models import DownloadRequest
from app.providers.base import DownloadError, DownloadResult, ProviderException
from app.providers.manager import manager
from app.services.subscription_service import consume_download
from app.workers.queue import dequeue

log = logging.getLogger("zed.worker")

# Per-error user-facing messages. fa is the primary market language; en is
# the fallback. NOTE: panel-managed bot_texts overrides are a v2 seam.
ERROR_TEXT: dict[str, dict[str, str]] = {
    "fa": {
        "unsupported_url": "این لینک پشتیبانی نمی‌شود. لطفاً یک لینک عمومی از پلتفرم‌های پشتیبانی‌شده بفرستید.",
        "private_content": "این محتوا خصوصی است و قابل دانلود نیست. فقط محتوای عمومی پشتیبانی می‌شود.",
        "not_found": "محتوایی در این لینک پیدا نشد؛ ممکن است حذف شده باشد.",
        "provider_down": "سرویس دانلود موقتاً در دسترس نیست. لطفاً کمی بعد دوباره تلاش کنید.",
        "rate_limited": "تعداد درخواست‌ها زیاد است؛ لطفاً چند دقیقه دیگر دوباره تلاش کنید.",
        "file_too_large": "حجم این فایل بیشتر از حد مجاز است و قابل ارسال نیست.",
        "duration_too_long": "مدت‌زمان این ویدیو بیشتر از حد مجاز است.",
        "unknown_error": "خطای غیرمنتظره‌ای رخ داد. لطفاً دوباره تلاش کنید.",
        "upload_failed": "دانلود انجام شد اما ارسال فایل به تلگرام ناموفق بود. لطفاً دوباره تلاش کنید.",
    },
    "en": {
        "unsupported_url": "This link is not supported. Please send a public link from a supported platform.",
        "private_content": "This content is private and cannot be downloaded. Only public content is supported.",
        "not_found": "No content was found at this link; it may have been removed.",
        "provider_down": "The download service is temporarily unavailable. Please try again later.",
        "rate_limited": "Too many requests right now; please try again in a few minutes.",
        "file_too_large": "This file is larger than the allowed size and cannot be sent.",
        "duration_too_long": "This video is longer than the allowed duration.",
        "unknown_error": "An unexpected error occurred. Please try again.",
        "upload_failed": "The download finished but sending the file to Telegram failed. Please try again.",
    },
}


def error_text(lang: str, code: str) -> str:
    table = ERROR_TEXT.get(lang) or ERROR_TEXT["en"]
    return table.get(code) or ERROR_TEXT["en"].get(code) or ERROR_TEXT["en"]["unknown_error"]


async def _send_text(bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id, text)
    except Exception as exc:  # user blocked the bot, chat gone, etc.
        log.warning("could not message chat %s: %s", chat_id, exc)


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


async def process_job(bot, payload: dict) -> None:
    settings = get_settings()
    request_id = payload.get("request_id")
    chat_id = payload.get("chat_id") or payload.get("telegram_id")
    lang = payload.get("language") or "fa"

    async with SessionLocal() as session:
        request = await session.get(DownloadRequest, request_id)
        if request is None or request.status != "queued":
            log.info("skipping job %s (missing or not queued)", request_id)
            return

        request.status = "processing"
        request.started_at = utcnow()
        await session.commit()

        os.makedirs(settings.TEMP_DIR, exist_ok=True)
        dest_dir = tempfile.mkdtemp(prefix=f"req{request.id}-", dir=settings.TEMP_DIR)
        try:
            try:
                provider_row, result = await asyncio.wait_for(
                    manager.download(session, request.url, request.platform_id, dest_dir),
                    timeout=settings.DOWNLOAD_TIMEOUT_SECONDS,
                )
            except (TimeoutError, asyncio.TimeoutError):
                await _fail(session, request, DownloadError.PROVIDER_DOWN.value)
                await _send_text(bot, chat_id, error_text(lang, "provider_down"))
                return
            except ProviderException as exc:
                await _fail(session, request, exc.code.value)
                await _send_text(bot, chat_id, error_text(lang, exc.code.value))
                return

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
        finally:
            shutil.rmtree(dest_dir, ignore_errors=True)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    settings = get_settings()
    os.makedirs(settings.TEMP_DIR, exist_ok=True)

    from aiogram import Bot  # lazy: keeps module importable without aiogram

    bot = Bot(token=settings.BOT_TOKEN)
    log.info("worker started, waiting for jobs on the queue")
    while True:
        try:
            payload = await dequeue(timeout=5)
        except Exception as exc:  # redis hiccup — back off and retry
            log.error("queue error: %s", exc)
            await asyncio.sleep(3)
            continue
        if payload is None:
            continue
        try:
            await process_job(bot, payload)
        except Exception:
            log.exception("unhandled error processing job %s", payload)


if __name__ == "__main__":
    asyncio.run(main())
