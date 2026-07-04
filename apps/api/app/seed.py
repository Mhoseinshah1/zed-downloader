"""Idempotent database seed. Runs on every API container start:

    python -m app.seed

Every block is get-or-create keyed on a unique column, so re-running never
duplicates rows and never overwrites operator edits made from the panel.
"""
import asyncio

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.models import (
    Admin,
    BotText,
    Language,
    Plan,
    Platform,
    Provider,
    Setting,
)
from app.utils.security import hash_password

# code, english name, native name, rtl. Only fa/en start active; the other 14
# are pre-registered so translations can be switched on from the panel later.
LANGUAGES: list[tuple[str, str, str, bool]] = [
    ("fa", "Persian", "فارسی", True),
    ("en", "English", "English", False),
    ("ar", "Arabic", "العربية", True),
    ("tr", "Turkish", "Türkçe", False),
    ("ru", "Russian", "Русский", False),
    ("hi", "Hindi", "हिन्दी", False),
    ("ur", "Urdu", "اردو", True),
    ("de", "German", "Deutsch", False),
    ("fr", "French", "Français", False),
    ("es", "Spanish", "Español", False),
    ("it", "Italian", "Italiano", False),
    ("pt", "Portuguese", "Português", False),
    ("zh", "Chinese", "中文", False),
    ("ja", "Japanese", "日本語", False),
    ("ko", "Korean", "한국어", False),
    ("id", "Indonesian", "Bahasa Indonesia", False),
]
ACTIVE_LANGUAGES = {"fa", "en"}

# name, slug, url_regex, sort_order — generic is the catch-all and must sort last.
PLATFORMS: list[tuple[str, str, str, int]] = [
    ("Instagram", "instagram", r"(?:instagram\.com|instagr\.am)/", 10),
    ("YouTube", "youtube", r"(?:youtube\.com|youtu\.be)/", 20),
    ("TikTok", "tiktok", r"(?:vm\.tiktok\.com|tiktok\.com)/", 30),
    ("Twitter / X", "twitter", r"(?:twitter\.com|x\.com)/", 40),
    ("Generic", "generic", r"^https?://", 999),
]

# name, slug, platform_slug, provider_type, priority
PROVIDERS: list[tuple[str, str, str, str, int]] = [
    ("Apify Instagram", "apify-instagram", "instagram", "apify", 10),
    ("yt-dlp YouTube", "ytdlp-youtube", "youtube", "ytdlp", 10),
    ("yt-dlp TikTok", "ytdlp-tiktok", "tiktok", "ytdlp", 10),
    ("yt-dlp Twitter", "ytdlp-twitter", "twitter", "ytdlp", 10),
    ("yt-dlp Generic", "ytdlp-generic", "generic", "ytdlp", 10),
]

# name, description, price (IRT/Toman), duration_days, download_limit (0=unlimited), sort
PLANS: list[tuple[str, str, int, int, int, int]] = [
    ("برنزی / Bronze", "۱۰۰ دانلود در ۳۰ روز — 100 downloads / 30 days", 190_000, 30, 100, 10),
    ("نقره‌ای / Silver", "۴۰۰ دانلود در ۹۰ روز — 400 downloads / 90 days", 490_000, 90, 400, 20),
    ("طلایی / Gold", "دانلود نامحدود در ۱۸۰ روز — unlimited / 180 days", 890_000, 180, 0, 30),
]

# key, default value, description
SETTINGS_DEFAULTS: list[tuple[str, str, str]] = [
    ("maintenance_mode", "false", "true = deny all downloads with a maintenance message"),
    ("free_downloads_per_day", "3", "free-tier daily download limit per user"),
    ("forced_join_enabled", "true", "true = bot enforces joining forced_join_channels"),
]

# Panel-editable copies of user-facing texts. The worker and bot resolve texts
# through texts_service, which falls back to these exact defaults when a row is
# missing — seeding DEFAULTS keeps the DB and code in lockstep while still
# letting operators edit the rows from the panel.
from app.services.texts_service import DEFAULTS as BOT_TEXTS  # noqa: E402


async def seed() -> None:
    settings = get_settings()
    created: dict[str, int] = {}

    async with SessionLocal() as session:
        # Languages ---------------------------------------------------------
        count = 0
        for order, (code, name, native, rtl) in enumerate(LANGUAGES):
            existing = (
                await session.execute(select(Language).where(Language.code == code))
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    Language(
                        code=code,
                        name=name,
                        native_name=native,
                        is_rtl=rtl,
                        is_active=code in ACTIVE_LANGUAGES,
                        sort_order=order,
                    )
                )
                count += 1
        created["languages"] = count

        # Settings ------------------------------------------------------------
        count = 0
        for key, value, description in SETTINGS_DEFAULTS:
            existing = (
                await session.execute(select(Setting).where(Setting.key == key))
            ).scalar_one_or_none()
            if existing is None:
                session.add(Setting(key=key, value=value, description=description))
                count += 1
        created["settings"] = count

        # Platforms -----------------------------------------------------------
        count = 0
        for name, slug, url_regex, sort_order in PLATFORMS:
            existing = (
                await session.execute(select(Platform).where(Platform.slug == slug))
            ).scalar_one_or_none()
            if existing is None:
                session.add(Platform(name=name, slug=slug, url_regex=url_regex, sort_order=sort_order))
                count += 1
        created["platforms"] = count
        await session.flush()

        platform_ids = {
            row.slug: row.id for row in (await session.execute(select(Platform))).scalars()
        }

        # Providers -------------------------------------------------------------
        count = 0
        for name, slug, platform_slug, provider_type, priority in PROVIDERS:
            existing = (
                await session.execute(select(Provider).where(Provider.slug == slug))
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    Provider(
                        name=name,
                        slug=slug,
                        platform_id=platform_ids[platform_slug],
                        provider_type=provider_type,
                        priority=priority,
                        # NOTE: the Apify provider needs its API key added from
                        # the panel before Instagram downloads work.
                    )
                )
                count += 1
        created["providers"] = count

        # Plans ------------------------------------------------------------------
        count = 0
        for name, description, price, duration_days, download_limit, sort_order in PLANS:
            existing = (
                await session.execute(select(Plan).where(Plan.name == name))
            ).scalar_one_or_none()
            if existing is None:
                session.add(
                    Plan(
                        name=name,
                        description=description,
                        price=price,
                        currency="IRT",
                        duration_days=duration_days,
                        download_limit=download_limit,
                        scope="user",
                        sort_order=sort_order,
                    )
                )
                count += 1
        created["plans"] = count

        # Owner admin ---------------------------------------------------------------
        email = settings.OWNER_ADMIN_EMAIL.lower()
        existing_admin = (
            await session.execute(select(Admin).where(Admin.email == email))
        ).scalar_one_or_none()
        if existing_admin is None:
            session.add(
                Admin(
                    email=email,
                    password_hash=hash_password(settings.OWNER_ADMIN_PASSWORD),
                    full_name="Owner",
                    role="owner",
                )
            )
            created["admins"] = 1
        else:
            # NOTE: existing owner is never overwritten — change the password
            # from the panel (v2) or directly in the DB.
            created["admins"] = 0

        # Bot texts ---------------------------------------------------------------------
        count = 0
        for key, translations in BOT_TEXTS.items():
            for lang, value in translations.items():
                existing = (
                    await session.execute(
                        select(BotText).where(BotText.key == key, BotText.lang == lang)
                    )
                ).scalar_one_or_none()
                if existing is None:
                    session.add(BotText(key=key, lang=lang, value=value))
                    count += 1
        created["bot_texts"] = count

        await session.commit()

    summary = ", ".join(f"{k}+{v}" for k, v in created.items())
    print(f"[seed] done ({summary})")


def main() -> None:
    asyncio.run(seed())


if __name__ == "__main__":
    main()
