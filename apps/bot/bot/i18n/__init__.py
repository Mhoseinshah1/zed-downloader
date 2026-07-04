"""Tiny i18n layer for bot strings.

Every ``*.json`` file in this directory is loaded at import time; the file
stem is the language code (fa.json -> "fa"). Adding a new language is just
dropping a new JSON file with the same flat, dot-separated key set -- the
loader and the language picker keyboard pick it up automatically (ready for
the planned 16 languages).
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_LANGUAGE = "en"
PRIMARY_LANGUAGE = "fa"  # primary market language, shown first in pickers

_DIR = Path(__file__).parent
_translations: dict[str, dict[str, str]] = {}

for _path in sorted(_DIR.glob("*.json")):
    try:
        with _path.open(encoding="utf-8") as fh:
            _translations[_path.stem] = json.load(fh)
    except (OSError, ValueError):
        # NOTE: a broken translation file must not take the bot down;
        # the fallback chain below covers missing languages.
        logger.exception("Failed to load translation file %s", _path)


def available_languages() -> list[str]:
    """Language codes with loaded translations, primary language first."""
    return sorted(_translations, key=lambda code: (code != PRIMARY_LANGUAGE, code))


def apply_overlay(texts_by_lang: dict[str, dict[str, str]] | None) -> None:
    """Overlay panel-edited texts on top of the bundled JSON, per lang + key.

    ``texts_by_lang`` maps a language code to a ``{key: value}`` mapping (the
    shape returned by ``GET /api/internal/texts``). Each string value replaces
    the bundled default for that lang + key so ``t()`` returns the DB value when
    present and the JSON default otherwise. Only languages that are already
    bundled are overlaid, and malformed entries are skipped so a bad payload can
    never wipe or corrupt the shipped translations.
    """
    if not texts_by_lang:
        return
    for lang, entries in texts_by_lang.items():
        if lang not in _translations or not isinstance(entries, dict):
            continue
        for key, value in entries.items():
            if isinstance(value, str):
                _translations[lang][key] = value


def t(lang: str | None, key: str, **kwargs: object) -> str:
    """Translate ``key`` for ``lang`` with fallback chain lang -> en -> key.

    Supports ``{placeholder}`` substitution via ``str.format``. A formatting
    error (e.g. a translator removed a placeholder) returns the raw string
    instead of raising.
    """
    text: str | None = None
    for candidate in (lang, DEFAULT_LANGUAGE):
        if candidate and candidate in _translations:
            text = _translations[candidate].get(key)
            if text is not None:
                break
    if text is None:
        return key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            logger.warning("Bad placeholders in i18n key %r (lang=%r)", key, lang)
            return text
    return text
