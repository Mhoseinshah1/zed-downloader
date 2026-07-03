"""Language picker keyboard built from every loaded translation."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.i18n import available_languages, t


def language_keyboard() -> InlineKeyboardMarkup:
    """One button per available language, labelled in its own language.

    Scales automatically when new i18n JSON files are added (each file only
    needs a native "lang.name" entry). Callback data: ``lang:<code>``.
    """
    rows = [
        [
            InlineKeyboardButton(
                text=t(code, "lang.name"), callback_data=f"lang:{code}"
            )
        ]
        for code in available_languages()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
