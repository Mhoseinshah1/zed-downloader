"""Main-menu button handlers (private chats).

Matches only the localized menu-button texts, so any other text falls through
to the download/intake router. Real payment/download stay out of Phase 2 —
Buy shows a placeholder and Download prompts for a link.
"""

import logging

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.types import Message

from bot.i18n import t
from bot.keyboards.language import language_keyboard
from bot.keyboards.menu import main_menu_keyboard, resolve_menu_action
from bot.services import api_client

logger = logging.getLogger(__name__)

router = Router(name="menu")


async def _menu_filter(message: Message) -> bool:
    """True only when the message text is one of the localized menu buttons."""
    return bool(message.text) and resolve_menu_action(message.text) is not None


def _account_language_label(code: str | None) -> str:
    # Show the account's language in its own name when we know it.
    return t(code or "en", "lang.name")


def render_account(account: dict, lang: str) -> str:
    """Build the 'My Account' text from the API account summary."""
    none = t(lang, "account.none")
    sub = account.get("subscription")
    if sub:
        subscription = t(
            lang,
            "account.subscription_active",
            expires_at=(sub.get("expires_at") or "")[:10] or none,
            plan_name=sub.get("plan_name") or none,
        )
        account_type = t(lang, "account.type_subscription")
    else:
        subscription = t(lang, "account.subscription_none")
        account_type = t(lang, "account.type_free")

    created = account.get("created_at")
    return t(
        lang,
        "account.body",
        telegram_id=account.get("telegram_id", none),
        username=account.get("username") or none,
        language=_account_language_label(account.get("language")),
        account_type=account_type,
        quota=account.get("free_daily_quota", none),
        subscription=subscription,
        created_at=(created or "")[:10] or none,
        total_downloads=account.get("total_downloads", 0),
    )


@router.message(ChatType.PRIVATE == F.chat.type, _menu_filter)
async def on_menu_button(message: Message, lang: str) -> None:
    action = resolve_menu_action(message.text)
    logger.info("menu button clicked: action=%s user=%s", action, message.from_user.id)

    if action == "download":
        await message.answer(t(lang, "download.prompt"))
        return

    if action == "change_language":
        await message.answer(t(lang, "start.choose_language"), reply_markup=language_keyboard())
        return

    if action == "help":
        await message.answer(t(lang, "help.text"))
        return

    if action == "buy":
        await message.answer(t(lang, "buy.body"))
        return

    if action == "account":
        account = await api_client.get_user_account(message.from_user.id)
        if account is None:
            await message.answer(t(lang, "errors.api_unreachable"))
            return
        await message.answer(render_account(account, lang), reply_markup=main_menu_keyboard(lang))
        return
