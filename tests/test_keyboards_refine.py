from __future__ import annotations

from bot.keyboards.refine import (
    CALLBACK_IMAGE_UPGRADE,
    CALLBACK_IMAGE_UPGRADE_DONE,
    CALLBACK_PACKAGE_PREFIX,
    CALLBACK_SITE_PUSH_PREFIX,
    build_image_upgrade_keyboard,
    build_image_upgraded_keyboard,
    build_refine_keyboard,
)
from bot.locales.loader import get_string


def _find_button(keyboard, text: str):
    # Looked up by label rather than by row index: the keyboard grows from the
    # bottom as new actions are added, and a positional assertion would break
    # every time an unrelated button is appended.
    for row in keyboard.inline_keyboard:
        for button in row:
            if button.text == text:
                return button
    raise AssertionError(f"button not found: {text}")


def test_includes_site_push_button():
    keyboard = build_refine_keyboard("telegram", 1, "ru")

    button = _find_button(keyboard, get_string("site_push_button", "ru"))
    assert button.callback_data == f"{CALLBACK_SITE_PUSH_PREFIX}:telegram:1"


def test_includes_social_media_package_button():
    keyboard = build_refine_keyboard("telegram", 1, "ru")

    button = _find_button(keyboard, get_string("package_button", "ru"))
    assert button.callback_data == f"{CALLBACK_PACKAGE_PREFIX}:telegram:1"


def test_image_upgrade_keyboard_has_single_button_with_price_in_label():
    keyboard = build_image_upgrade_keyboard("ru")

    assert len(keyboard.inline_keyboard) == 1
    assert len(keyboard.inline_keyboard[0]) == 1
    button = keyboard.inline_keyboard[0][0]
    assert button.text == get_string("image_upgrade_button", "ru")
    assert button.callback_data == CALLBACK_IMAGE_UPGRADE


def test_image_upgraded_keyboard_has_single_disabled_style_button():
    keyboard = build_image_upgraded_keyboard("ru")

    assert len(keyboard.inline_keyboard) == 1
    assert len(keyboard.inline_keyboard[0]) == 1
    button = keyboard.inline_keyboard[0][0]
    assert button.text == get_string("image_upgraded_button", "ru")
    assert button.callback_data == CALLBACK_IMAGE_UPGRADE_DONE
