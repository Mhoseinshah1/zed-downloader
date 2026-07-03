"""Forced-join keyboard: join links for missing channels + a verify button."""

from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import t

VERIFY_CALLBACK = "fj:verify"


def forced_join_keyboard(
    channels: list[dict[str, Any]], lang: str
) -> InlineKeyboardMarkup:
    """URL buttons to https://t.me/<username> plus an "I joined" verify button.

    Channels without a public username cannot be linked to, so they are
    skipped here (the membership check still covers them via channel_id).
    """
    rows: list[list[InlineKeyboardButton]] = []
    for channel in channels:
        username = (channel.get("username") or "").lstrip("@")
        if not username:
            continue
        title = channel.get("title") or f"@{username}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=t(lang, "forced_join.button", title=title),
                    url=f"https://t.me/{username}",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=t(lang, "forced_join.verify"), callback_data=VERIFY_CALLBACK
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
