from __future__ import annotations

from bot.keyboards.refine import build_refine_keyboard
from bot.locales.loader import get_string
from bot.services import output_formatter


def test_format_variant_escapes_html_special_characters():
    text = "Скидка 50%! <b>fake bold</b> & больше деталей"

    formatted = output_formatter.format_variant(text)

    assert "<b>" not in formatted
    assert "</b>" not in formatted
    assert "&lt;b&gt;" in formatted
    assert "&lt;/b&gt;" in formatted
    assert "&amp;" in formatted


def test_format_variant_leaves_plain_text_and_emoji_untouched():
    text = "Готово! 🚀 Подпишись сейчас, не пожалеешь."

    assert output_formatter.format_variant(text) == text


def test_format_variant_does_not_double_escape_ampersand():
    assert output_formatter.format_variant("AT&T") == "AT&amp;T"


def test_format_variant_output_has_no_unescaped_angle_brackets():
    text = "5 < 10, но 20 > 10 <script>evil()</script>"

    formatted = output_formatter.format_variant(text)

    assert "<" not in formatted.replace("&lt;", "").replace("&gt;", "")
    assert ">" not in formatted.replace("&lt;", "").replace("&gt;", "")


def test_build_refine_keyboard_has_two_buttons_with_platform_and_index_encoded():
    keyboard = build_refine_keyboard("telegram", 1, "ru")

    row = keyboard.inline_keyboard[0]
    assert len(row) == 2
    assert row[0].callback_data == "refine:more:telegram:1"
    assert row[1].callback_data == "refine:shorten:telegram:1"


def test_build_refine_keyboard_encodes_vk_platform():
    keyboard = build_refine_keyboard("vk", 2, "ru")

    row = keyboard.inline_keyboard[0]
    assert row[0].callback_data == "refine:more:vk:2"
    assert row[1].callback_data == "refine:shorten:vk:2"


def test_build_refine_keyboard_callback_data_within_telegram_64_byte_limit():
    keyboard = build_refine_keyboard("telegram", 999999, "ru")

    for button in keyboard.inline_keyboard[0]:
        assert len(button.callback_data.encode("utf-8")) <= 64


def test_build_refine_keyboard_uses_localized_button_text():
    keyboard = build_refine_keyboard("telegram", 1, "en")

    row = keyboard.inline_keyboard[0]
    assert row[0].text == get_string("refine_more_button", "en")
    assert row[1].text == get_string("refine_shorten_button", "en")


def test_build_refine_keyboard_has_publish_button_encoding_platform_and_index():
    keyboard = build_refine_keyboard("telegram", 1, "ru")

    publish_row = keyboard.inline_keyboard[1]
    assert len(publish_row) == 1
    assert publish_row[0].callback_data == "refine:publish:telegram:1"
    assert publish_row[0].text == get_string("publish_to_channel_button", "ru")


def test_build_refine_keyboard_publish_button_encodes_vk_platform():
    keyboard = build_refine_keyboard("vk", 2, "ru")

    publish_row = keyboard.inline_keyboard[1]
    assert publish_row[0].callback_data == "refine:publish:vk:2"


def test_build_refine_keyboard_publish_callback_data_within_telegram_64_byte_limit():
    keyboard = build_refine_keyboard("telegram", 999999, "ru")

    publish_row = keyboard.inline_keyboard[1]
    assert len(publish_row[0].callback_data.encode("utf-8")) <= 64


def test_build_refine_keyboard_has_image_button_encoding_platform_and_index():
    keyboard = build_refine_keyboard("telegram", 1, "ru")

    image_row = keyboard.inline_keyboard[2]
    assert image_row[0].callback_data == "refine:image:telegram:1"
    assert image_row[0].text == get_string("generate_image_button", "ru")


def test_build_refine_keyboard_image_button_encodes_vk_platform():
    keyboard = build_refine_keyboard("vk", 2, "ru")

    image_row = keyboard.inline_keyboard[2]
    assert image_row[0].callback_data == "refine:image:vk:2"


def test_build_refine_keyboard_image_callback_data_within_telegram_64_byte_limit():
    keyboard = build_refine_keyboard("telegram", 999999, "ru")

    image_row = keyboard.inline_keyboard[2]
    assert len(image_row[0].callback_data.encode("utf-8")) <= 64
