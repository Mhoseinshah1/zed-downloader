"""/help command."""

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.i18n import t

router = Router(name="help")


@router.message(Command("help"))
async def cmd_help(message: Message, lang: str) -> None:
    await message.answer(t(lang, "help.text"))
