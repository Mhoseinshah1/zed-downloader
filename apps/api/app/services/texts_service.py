"""Database-backed, panel-editable user-facing texts.

`bot_texts` rows (key, lang, value) are the source of truth. The worker and
the bot read texts through a small in-memory cache that is refreshed
periodically, always falling back to shipped defaults so a missing/edited row
can never break message delivery.

Fallback chain for text(lang, key): DB[lang] -> DB[en] -> DEFAULTS[lang] ->
DEFAULTS[en] -> the key itself.
"""
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import BotText

log = logging.getLogger("zed.texts")

# Shipped defaults (also seeded into bot_texts). Keyed key -> lang -> value.
# error.<DownloadError value> messages are used by the worker; the rest by the
# bot. Persian is primary; English is the universal fallback.
DEFAULTS: dict[str, dict[str, str]] = {
    "welcome": {
        "fa": "سلام! لینک عمومی از اینستاگرام، یوتیوب، تیک‌تاک یا توییتر بفرست تا برات دانلود کنم.",
        "en": "Hi! Send a public link from Instagram, YouTube, TikTok or Twitter and I'll download it for you.",
    },
    "help": {
        "fa": "کافی است یک لینک عمومی بفرستید. فقط محتوای عمومی پشتیبانی می‌شود.",
        "en": "Just send a public link. Only public content is supported.",
    },
    "download.queued": {
        "fa": "درخواست شما در صف قرار گرفت؛ فایل به‌زودی ارسال می‌شود.",
        "en": "Your request is queued; the file will arrive shortly.",
    },
    "error.unsupported_url": {
        "fa": "این لینک پشتیبانی نمی‌شود. لطفاً یک لینک عمومی از پلتفرم‌های پشتیبانی‌شده بفرستید.",
        "en": "This link is not supported. Please send a public link from a supported platform.",
    },
    "error.private_content": {
        "fa": "این محتوا خصوصی است و قابل دانلود نیست. فقط محتوای عمومی پشتیبانی می‌شود.",
        "en": "This content is private and cannot be downloaded. Only public content is supported.",
    },
    "error.not_found": {
        "fa": "محتوایی در این لینک پیدا نشد؛ ممکن است حذف شده باشد.",
        "en": "No content was found at this link; it may have been removed.",
    },
    "error.provider_down": {
        "fa": "سرویس دانلود موقتاً در دسترس نیست. لطفاً کمی بعد دوباره تلاش کنید.",
        "en": "The download service is temporarily unavailable. Please try again later.",
    },
    "error.rate_limited": {
        "fa": "تعداد درخواست‌ها زیاد است؛ لطفاً چند دقیقه دیگر دوباره تلاش کنید.",
        "en": "Too many requests right now; please try again in a few minutes.",
    },
    "error.file_too_large": {
        "fa": "حجم این فایل بیشتر از حد مجاز است و قابل ارسال نیست.",
        "en": "This file is larger than the allowed size and cannot be sent.",
    },
    "error.duration_too_long": {
        "fa": "مدت‌زمان این ویدیو بیشتر از حد مجاز است.",
        "en": "This video is longer than the allowed duration.",
    },
    "error.unknown_error": {
        "fa": "خطای غیرمنتظره‌ای رخ داد. لطفاً دوباره تلاش کنید.",
        "en": "An unexpected error occurred. Please try again.",
    },
    "error.upload_failed": {
        "fa": "دانلود انجام شد اما ارسال فایل به تلگرام ناموفق بود. لطفاً دوباره تلاش کنید.",
        "en": "The download finished but sending the file to Telegram failed. Please try again.",
    },
    "payment.confirmed": {
        "fa": "✅ پرداخت شما تأیید شد و اشتراک‌تان فعال است.",
        "en": "✅ Your payment was verified and your subscription is now active.",
    },
}

# key -> lang -> value, populated from the DB by refresh().
_cache: dict[str, dict[str, str]] = {}
_loaded = False


async def refresh(session: AsyncSession) -> int:
    """Reload the cache from bot_texts. Returns the number of rows loaded."""
    global _cache, _loaded
    rows = (await session.execute(select(BotText))).scalars().all()
    new: dict[str, dict[str, str]] = {}
    for row in rows:
        new.setdefault(row.key, {})[row.lang] = row.value
    _cache = new
    _loaded = True
    return len(rows)


def text(lang: str, key: str, **fmt) -> str:
    """Resolve a text with the DB-first fallback chain and optional
    str.format placeholders. Safe to call before refresh() (uses defaults)."""
    lang = lang or "en"
    for source in (_cache, DEFAULTS):
        table = source.get(key)
        if table:
            value = table.get(lang) or table.get("en")
            if value is not None:
                return value.format(**fmt) if fmt else value
    return key
