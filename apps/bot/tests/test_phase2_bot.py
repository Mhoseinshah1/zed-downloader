"""Phase 2 bot unit tests: URL validation, platform detection, menu text +
resolution, and the account renderer. Pure functions only — no Telegram."""
import json
from pathlib import Path

import pytest

from bot.handlers.download import (
    detect_platform,
    extract_url,
    is_valid_url,
    platform_display,
)
from bot.handlers.menu import render_account
from bot.i18n import t
from bot.keyboards.menu import MENU_KEYS, main_menu_keyboard, resolve_menu_action

_I18N = Path(__file__).resolve().parents[1] / "bot" / "i18n"


# --- i18n parity + menu text -------------------------------------------------

def test_fa_en_key_sets_identical():
    fa = json.load(open(_I18N / "fa.json", encoding="utf-8"))
    en = json.load(open(_I18N / "en.json", encoding="utf-8"))
    assert set(fa) == set(en)


def test_menu_texts_present_both_languages():
    for lang in ("fa", "en"):
        for key in MENU_KEYS:
            assert t(lang, key) != key, f"missing {key} for {lang}"


def test_menu_keyboard_has_five_buttons():
    kb = main_menu_keyboard("en")
    labels = [btn.text for row in kb.keyboard for btn in row]
    assert len(labels) == 5
    assert "📥 Download" in labels and "🌐 Change Language" in labels


# --- menu resolution ----------------------------------------------------------

@pytest.mark.parametrize(
    "text,action",
    [
        ("📥 دانلود", "download"),
        ("📥 Download", "download"),
        ("👤 My Account", "account"),
        ("👤 حساب من", "account"),
        ("💳 خرید اشتراک", "buy"),
        ("📚 Help", "help"),
        ("🌐 تغییر زبان", "change_language"),
        ("random text", None),
        ("", None),
        (None, None),
    ],
)
def test_resolve_menu_action(text, action):
    assert resolve_menu_action(text) == action


# --- URL validation + platform detection -------------------------------------

@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://www.instagram.com/p/Cabc/", "instagram"),
        ("https://instagr.am/p/x", "instagram"),
        ("https://youtu.be/dQw4", "youtube"),
        ("https://www.youtube.com/watch?v=x", "youtube"),
        ("https://vm.tiktok.com/ZM/", "tiktok"),
        ("https://www.tiktok.com/@a/video/1", "tiktok"),
        ("https://x.com/a/status/1", "twitter"),
        ("https://twitter.com/a", "twitter"),
        ("https://example.com/page", "generic"),
        ("https://box.com/x", "generic"),          # not x.com
        ("hello world", None),
        ("youtube.com no scheme", None),           # not an http(s) URL
        (None, None),
    ],
)
def test_detect_platform(url, expected):
    assert detect_platform(url) == expected


def test_is_valid_url():
    assert is_valid_url("go https://a.com now")
    assert not is_valid_url("just text")
    assert not is_valid_url("")
    assert not is_valid_url(None)


def test_extract_url_returns_first():
    assert extract_url("see https://a.com/1 and https://b.com/2") == "https://a.com/1"


def test_platform_display():
    assert platform_display("twitter") == "X / Twitter"
    assert platform_display("unknown") == "?"
    assert platform_display(None) == "?"


# --- account renderer ---------------------------------------------------------

def test_render_account_free():
    acc = {
        "telegram_id": 42, "username": "ali", "language": "fa", "total_downloads": 3,
        "created_at": "2026-07-01T10:00:00+00:00", "free_daily_quota": 3, "subscription": None,
    }
    txt = render_account(acc, "fa")
    assert "42" in txt and "ali" in txt
    assert t("fa", "account.subscription_none") in txt
    assert "2026-07-01" in txt  # date only, time trimmed


def test_render_account_with_subscription():
    acc = {
        "telegram_id": 7, "username": None, "language": "en", "total_downloads": 0,
        "created_at": "2026-07-01T10:00:00+00:00", "free_daily_quota": 3,
        "subscription": {"plan_name": "Gold", "expires_at": "2026-08-01T00:00:00+00:00",
                         "downloads_used": 2, "download_limit": 100},
    }
    txt = render_account(acc, "en")
    assert "Gold" in txt and "Active until 2026-08-01" in txt
    assert t("en", "account.none") in txt  # username None -> dash
