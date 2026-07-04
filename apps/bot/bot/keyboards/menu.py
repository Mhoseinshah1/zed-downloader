"""Main-menu reply keyboard and button-text -> action resolution.

The menu is a persistent reply keyboard (localized labels). Because a tapped
reply-keyboard button arrives as a plain text message equal to the button
label, we resolve an incoming text back to an action by matching it against
the menu labels of every loaded language.
"""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from bot.i18n import available_languages, t

# i18n key -> stable action name used by the menu handler.
MENU_KEYS: dict[str, str] = {
    "menu.download": "download",
    "menu.account": "account",
    "menu.buy": "buy",
    "menu.help": "help",
    "menu.change_language": "change_language",
}


def main_menu_keyboard(lang: str) -> ReplyKeyboardMarkup:
    """The localized main menu shown after language selection."""
    rows = [
        [KeyboardButton(text=t(lang, "menu.download"))],
        [KeyboardButton(text=t(lang, "menu.account")), KeyboardButton(text=t(lang, "menu.buy"))],
        [KeyboardButton(text=t(lang, "menu.help")), KeyboardButton(text=t(lang, "menu.change_language"))],
    ]
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def resolve_menu_action(text: str | None) -> str | None:
    """Return the action for a menu-button text, or None if it is not one.

    Checks every loaded language so a button tapped right after a language
    switch (keyboard still in the old language) still resolves.
    """
    if not text:
        return None
    for lang in available_languages():
        for key, action in MENU_KEYS.items():
            if t(lang, key) == text:
                return action
    return None
