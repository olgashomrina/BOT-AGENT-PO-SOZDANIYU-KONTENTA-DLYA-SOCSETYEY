from __future__ import annotations

from bot.keyboards.site import PILOT_BLOCK, PILOT_PAGE, build_site_menu_keyboard
from bot.locales.loader import get_string


def test_includes_open_site_button_when_url_set():
    keyboard = build_site_menu_keyboard("https://olgashomrina.github.io/my-lending-test/", "ru")

    first_row = keyboard.inline_keyboard[0]
    assert first_row[0].text == get_string("open_site_button", "ru")
    assert first_row[0].web_app.url == "https://olgashomrina.github.io/my-lending-test/"


def test_omits_open_site_button_when_url_missing():
    keyboard = build_site_menu_keyboard("", "ru")

    assert len(keyboard.inline_keyboard) == 1
    assert keyboard.inline_keyboard[0][0].callback_data == f"site:pull:{PILOT_PAGE}:{PILOT_BLOCK}"


def test_pull_button_text_and_callback_data():
    keyboard = build_site_menu_keyboard("https://example.com/", "en")

    pull_button = keyboard.inline_keyboard[-1][0]
    assert pull_button.text == get_string("pull_from_site_button", "en")
    assert pull_button.callback_data == f"site:pull:{PILOT_PAGE}:{PILOT_BLOCK}"
