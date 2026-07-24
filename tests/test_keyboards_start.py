from __future__ import annotations

from bot.keyboards.start import (
    CALLBACK_CAPABILITIES,
    CALLBACK_CREATE_POST,
    CALLBACK_PHOTO_GEN,
    CALLBACK_TEXT_HINT,
    build_create_post_keyboard,
    build_persistent_start_keyboard,
    build_start_menu_keyboard,
)
from bot.locales.loader import get_string


def test_persistent_start_keyboard_has_one_resizable_button():
    keyboard = build_persistent_start_keyboard("ru")

    assert keyboard.resize_keyboard is True
    assert len(keyboard.keyboard) == 1
    assert len(keyboard.keyboard[0]) == 1
    assert keyboard.keyboard[0][0].text == get_string("start_button_label", "ru")


def test_start_menu_keyboard_has_capabilities_and_cta_buttons():
    keyboard = build_start_menu_keyboard("en")

    assert keyboard.inline_keyboard[0][0].text == get_string("menu_capabilities_button", "en")
    assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_CAPABILITIES
    assert keyboard.inline_keyboard[1][0].text == get_string("menu_cta_button", "en")
    assert keyboard.inline_keyboard[1][0].callback_data == CALLBACK_CREATE_POST


def test_create_post_keyboard_includes_site_button_when_url_set():
    keyboard = build_create_post_keyboard("https://olgashomrina.github.io/my-lending-test/", "ru")

    first_row = keyboard.inline_keyboard[0]
    assert first_row[0].text == get_string("open_site_button", "ru")
    assert first_row[0].web_app.url == "https://olgashomrina.github.io/my-lending-test/"


def test_create_post_keyboard_omits_site_button_when_url_missing():
    keyboard = build_create_post_keyboard("", "ru")

    assert len(keyboard.inline_keyboard) == 2
    assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_TEXT_HINT
    assert keyboard.inline_keyboard[1][0].callback_data == CALLBACK_PHOTO_GEN


def test_create_post_keyboard_text_and_photo_buttons():
    keyboard = build_create_post_keyboard("https://example.com/", "vi")

    text_button = keyboard.inline_keyboard[-2][0]
    photo_button = keyboard.inline_keyboard[-1][0]
    assert text_button.text == get_string("menu_text_generation_button", "vi")
    assert text_button.callback_data == CALLBACK_TEXT_HINT
    assert photo_button.text == get_string("menu_photo_generation_button", "vi")
    assert photo_button.callback_data == CALLBACK_PHOTO_GEN
