from __future__ import annotations

from bot.keyboards.refine import CALLBACK_SITE_PUSH_PREFIX, build_refine_keyboard
from bot.locales.loader import get_string


def test_includes_site_push_button():
    keyboard = build_refine_keyboard("telegram", 1, "ru")

    last_row = keyboard.inline_keyboard[-1]
    assert last_row[0].text == get_string("site_push_button", "ru")
    assert last_row[0].callback_data == f"{CALLBACK_SITE_PUSH_PREFIX}:telegram:1"
