"""/start and /lang commands."""

import html

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.i18n import t
from bot.keyboards.language import language_keyboard

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, lang: str) -> None:
    # NOTE: the users/upsert response does not flag newly created users, so
    # the language picker is shown on every /start; picking a language is a
    # cheap idempotent action.
    name = html.escape(message.from_user.first_name or "")
    text = (
        t(lang, "start.welcome", name=name)
        + "\n\n"
        + t(lang, "start.choose_language")
    )
    await message.answer(text, reply_markup=language_keyboard())


@router.message(Command("lang"))
async def cmd_lang(message: Message, lang: str) -> None:
    await message.answer(
        t(lang, "start.choose_language"), reply_markup=language_keyboard()
    )
