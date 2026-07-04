"""/plans command and buy:<plan_id> purchase callbacks."""

import html
from decimal import Decimal, InvalidOperation
from typing import Any

from aiogram import F, Router
from aiogram.enums import ChatType
from aiogram.filters import Command
from aiogram.types import Chat, CallbackQuery, Message

from bot.i18n import t
from bot.keyboards.plans import pay_keyboard, plans_keyboard
from bot.services import api_client

router = Router(name="plans")

_GROUP_TYPES = {ChatType.GROUP, ChatType.SUPERGROUP}


def scope_and_chat_id(chat: Chat) -> tuple[str, int | None]:
    """Map a chat to (plans scope, payment chat_id).

    Group chats use group-scope plans and must carry the negative group id;
    private chats use user-scope plans with no chat_id.
    """
    if chat.type in _GROUP_TYPES:
        return "group", chat.id
    return "user", None


def format_price(value: Any) -> str:
    """Thousands-separated price string.

    The API serializes ``plan.price`` (a Decimal) as a JSON string, e.g.
    ``"190000.00"``, so coerce via Decimal (not float, which would round)
    before applying numeric formatting; fall back to the raw value.
    """
    try:
        return f"{Decimal(str(value)):,}"
    except InvalidOperation:
        return str(value)


def render_plans_text(plans: list[dict[str, Any]], lang: str) -> str:
    """Title plus one formatted line per plan."""
    lines = [t(lang, "plans.title"), ""]
    for plan in plans:
        # NOTE: currency is displayed as delivered by the API (e.g. "IRT");
        # currency-name localization can be added with the extra languages.
        lines.append(
            t(
                lang,
                "plans.item",
                name=html.escape(str(plan.get("name", ""))),
                price=format_price(plan.get("price", 0)),
                currency=html.escape(str(plan.get("currency", ""))),
                duration_days=plan.get("duration_days", 0),
                download_limit=plan.get("download_limit", 0),
            )
        )
    return "\n".join(lines)


@router.message(Command("plans"))
async def cmd_plans(message: Message, lang: str) -> None:
    scope, _ = scope_and_chat_id(message.chat)
    plans = await api_client.get_plans(scope=scope)
    if plans is None:
        await message.answer(t(lang, "errors.api_unreachable"))
        return
    if not plans:
        key = "plans.group_empty" if scope == "group" else "plans.empty"
        await message.answer(t(lang, key))
        return
    await message.answer(
        render_plans_text(plans, lang), reply_markup=plans_keyboard(plans, lang)
    )


@router.callback_query(F.data.startswith("buy:"))
async def buy_plan(callback: CallbackQuery, lang: str) -> None:
    try:
        plan_id = int(callback.data.split(":", 1)[1])
    except ValueError:
        await callback.answer()
        return

    # The chat the buy button lives in decides the scope: a group needs its
    # negative chat_id passed to the payment call; a private chat sends none.
    _, chat_id = scope_and_chat_id(callback.message.chat)
    payment = await api_client.create_payment(
        telegram_id=callback.from_user.id,
        plan_id=plan_id,
        gateway="zarinpal",
        chat_id=chat_id,
    )
    if payment is None or not payment.get("payment_url"):
        await callback.answer(t(lang, "payment.failed"), show_alert=True)
        return

    await callback.answer()
    await callback.message.answer(
        t(lang, "payment.link_ready"),
        reply_markup=pay_keyboard(payment["payment_url"], lang),
    )
