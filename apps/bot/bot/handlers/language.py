"""Language selection callback: persist via the API, confirm in the new language."""

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery

from bot.i18n import available_languages, t
from bot.middlewares.user import set_cached_language
from bot.services import api_client

router = Router(name="language")


@router.callback_query(F.data.startswith("lang:"))
async def language_selected(callback: CallbackQuery) -> None:
    new_lang = callback.data.split(":", 1)[1]
    if new_lang not in available_languages():
        await callback.answer()
        return

    result = await api_client.set_language(callback.from_user.id, new_lang)
    if result is None:
        await callback.answer(
            t(new_lang, "errors.api_unreachable"), show_alert=True
        )
        return

    # Keep the middleware TTL cache in sync so the very next message already
    # uses the newly chosen language.
    set_cached_language(callback.from_user.id, new_lang)

    await callback.answer()
    confirmation = t(new_lang, "lang.changed")
    try:
        await callback.message.edit_text(confirmation)
    except TelegramAPIError:
        # Message may be too old to edit or unchanged; send a fresh one.
        await callback.message.answer(confirmation)
