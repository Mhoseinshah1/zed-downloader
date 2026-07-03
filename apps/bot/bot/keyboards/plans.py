"""Keyboards for subscription plans and payment links."""

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import t


def plans_keyboard(plans: list[dict[str, Any]], lang: str) -> InlineKeyboardMarkup:
    """One "buy" button per plan. Callback data: ``buy:<plan_id>``."""
    rows = [
        [
            InlineKeyboardButton(
                text=t(lang, "plans.buy_button", name=plan.get("name", "")),
                callback_data=f"buy:{plan['id']}",
            )
        ]
        for plan in plans
        if plan.get("id") is not None
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def pay_keyboard(payment_url: str, lang: str) -> InlineKeyboardMarkup:
    """A single URL button that opens the payment gateway page."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t(lang, "payment.pay_button"), url=payment_url)]
        ]
    )
