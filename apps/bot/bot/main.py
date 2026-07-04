"""Bot entrypoint: polling (default) or webhook mode, per RUN_MODE."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot import i18n
from bot.config import Settings, get_settings
from bot.handlers import download, help as help_handler, language, menu, plans, start
from bot.middlewares.user import UserMiddleware
from bot.services import api_client

logger = logging.getLogger(__name__)

WEBHOOK_PATH = "/webhook/telegram"


async def load_texts_overlay() -> None:
    """Best-effort overlay of panel-edited texts onto the bundled i18n.

    Runs once at startup (both polling and webhook modes). A fetch failure must
    NOT crash the bot -- we simply keep the bundled JSON defaults. This is a
    startup-only overlay; a periodic refresh could be added later if needed.
    """
    try:
        texts = await api_client.get_texts()
    except Exception:  # pragma: no cover - defensive; get_texts already guards
        logger.exception("Failed to fetch editable texts overlay; keeping JSON")
        return
    if not texts:
        logger.info("No editable texts overlay applied; using bundled i18n")
        return
    i18n.apply_overlay(texts)
    logger.info("Applied editable texts overlay for %d language(s)", len(texts))


def build_dispatcher() -> Dispatcher:
    dp = Dispatcher()

    middleware = UserMiddleware()
    dp.message.middleware(middleware)
    dp.callback_query.middleware(middleware)

    # Order matters: the download router has a catch-all text handler for
    # private chats, so command routers AND the menu router (which matches only
    # menu-button texts) must be registered before it.
    dp.include_router(start.router)
    dp.include_router(language.router)
    dp.include_router(menu.router)
    dp.include_router(help_handler.router)
    dp.include_router(plans.router)
    dp.include_router(download.router)

    dp.startup.register(load_texts_overlay)
    dp.shutdown.register(api_client.close_client)
    return dp


async def run_polling(bot: Bot, dp: Dispatcher) -> None:
    await bot.delete_webhook(drop_pending_updates=False)
    logger.info("bot started (polling mode)")
    await dp.start_polling(bot)


def run_webhook(bot: Bot, dp: Dispatcher, settings: Settings) -> None:
    webhook_url = settings.webhook_base_url.rstrip("/") + WEBHOOK_PATH

    async def on_startup(bot: Bot) -> None:
        await bot.set_webhook(
            url=webhook_url,
            secret_token=settings.telegram_webhook_secret,
            drop_pending_updates=False,
        )
        logger.info("Webhook set to %s", webhook_url)

    dp.startup.register(on_startup)

    app = web.Application()
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.telegram_webhook_secret,
    ).register(app, path=WEBHOOK_PATH)
    setup_application(app, dp, bot=bot)

    logger.info("Starting bot in webhook mode on 0.0.0.0:%s", settings.webhook_port)
    web.run_app(app, host="0.0.0.0", port=settings.webhook_port)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    if not settings.bot_token:
        raise SystemExit("BOT_TOKEN is not set")

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = build_dispatcher()

    if settings.run_mode.strip().lower() == "webhook":
        if not settings.webhook_base_url:
            raise SystemExit("WEBHOOK_BASE_URL is required when RUN_MODE=webhook")
        run_webhook(bot, dp, settings)
    else:
        asyncio.run(run_polling(bot, dp))


if __name__ == "__main__":
    main()
