"""/plans command and buy:<plan_id> purchase callbacks."""

import html
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.i18n import t
from bot.keyboards.plans import pay_keyboard, plans_keyboard
from bot.services import api_client

router = Router(name="plans")


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
                price=f"{plan.get('price', 0):,}",
                currency=html.escape(str(plan.get("currency", ""))),
                duration_days=plan.get("duration_days", 0),
                download_limit=plan.get("download_limit", 0),
            )
        )
    return "\n".join(lines)


@router.message(Command("plans"))
async def cmd_plans(message: Message, lang: str) -> None:
    plans = await api_client.get_plans()
    if plans is None:
        await message.answer(t(lang, "errors.api_unreachable"))
        return
    if not plans:
        await message.answer(t(lang, "plans.empty"))
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

    payment = await api_client.create_payment(
        telegram_id=callback.from_user.id, plan_id=plan_id, gateway="zarinpal"
    )
    if payment is None or not payment.get("payment_url"):
        await callback.answer(t(lang, "payment.failed"), show_alert=True)
        return

    await callback.answer()
    await callback.message.answer(
        t(lang, "payment.link_ready"),
        reply_markup=pay_keyboard(payment["payment_url"], lang),
    )
