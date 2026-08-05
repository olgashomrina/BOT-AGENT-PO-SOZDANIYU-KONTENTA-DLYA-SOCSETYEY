from __future__ import annotations

from bot.keyboards.start import (
    CALLBACK_CAPABILITIES,
    CALLBACK_CREATE_POST,
    CALLBACK_NEWS_DIGEST,
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


def test_start_menu_keyboard_has_news_digest_button():
    keyboard = build_start_menu_keyboard("ru")

    assert keyboard.inline_keyboard[2][0].text == get_string("menu_news_digest_button", "ru")
    assert keyboard.inline_keyboard[2][0].callback_data == CALLBACK_NEWS_DIGEST


def test_create_post_keyboard_includes_site_button_when_url_set():
    keyboard = build_create_post_keyboard(
        "https://olgashomrina.github.io/my-lending-test/", "ru", "medium"
    )

    first_row = keyboard.inline_keyboard[0]
    assert first_row[0].text == get_string("open_site_button", "ru")
    assert first_row[0].web_app.url == "https://olgashomrina.github.io/my-lending-test/"


def test_create_post_keyboard_omits_site_button_when_url_missing():
    keyboard = build_create_post_keyboard("", "ru", "medium")

    assert len(keyboard.inline_keyboard) == 3
    assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_TEXT_HINT
    assert keyboard.inline_keyboard[1][0].callback_data == CALLBACK_PHOTO_GEN
    assert keyboard.inline_keyboard[2][0].callback_data == CALLBACK_POST_LENGTH


def test_create_post_keyboard_text_and_photo_buttons():
    keyboard = build_create_post_keyboard("https://example.com/", "vi", "medium")

    text_button = keyboard.inline_keyboard[-3][0]
    photo_button = keyboard.inline_keyboard[-2][0]
    assert text_button.text == get_string("menu_text_generation_button", "vi")
    assert text_button.callback_data == CALLBACK_TEXT_HINT
    assert photo_button.text == get_string("menu_photo_generation_button", "vi")
    assert photo_button.callback_data == CALLBACK_PHOTO_GEN


from bot.keyboards.start import CALLBACK_DIGEST_SET_TOPIC, build_digest_topic_keyboard


def test_digest_topic_keyboard_shows_write_label_when_no_saved_topic():
    keyboard = build_digest_topic_keyboard("ru", has_saved_topic=False)

    assert keyboard.inline_keyboard[0][0].text == get_string("menu_digest_write_topic_button", "ru")
    assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_DIGEST_SET_TOPIC


def test_digest_topic_keyboard_shows_change_label_when_topic_saved():
    keyboard = build_digest_topic_keyboard("en", has_saved_topic=True)

    assert keyboard.inline_keyboard[0][0].text == get_string("menu_digest_change_topic_button", "en")
    assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_DIGEST_SET_TOPIC


from bot.keyboards.authorpost import CALLBACK_START as CALLBACK_AUTHORPOST_START


def test_digest_topic_keyboard_includes_authorpost_button():
    keyboard = build_digest_topic_keyboard("ru", has_saved_topic=True)

    assert len(keyboard.inline_keyboard) == 2
    assert keyboard.inline_keyboard[1][0].text == get_string("authorpost_button", "ru")
    assert keyboard.inline_keyboard[1][0].callback_data == CALLBACK_AUTHORPOST_START


def test_digest_topic_keyboard_includes_authorpost_button_without_saved_topic():
    keyboard = build_digest_topic_keyboard("en", has_saved_topic=False)

    assert keyboard.inline_keyboard[1][0].callback_data == CALLBACK_AUTHORPOST_START


def test_start_menu_offers_my_double():
    from bot.keyboards.circle import CALLBACK_MY_DOUBLE

    markup = build_start_menu_keyboard("ru")

    callbacks = [
        button.callback_data for row in markup.inline_keyboard for button in row
    ]

    assert CALLBACK_MY_DOUBLE in callbacks


from bot.keyboards.start import (
    CALLBACK_POST_LENGTH,
    CALLBACK_POST_LENGTH_SET_PREFIX,
    build_post_length_keyboard,
)
from bot.services import post_length


def test_create_post_keyboard_shows_the_current_post_length():
    keyboard = build_create_post_keyboard("", "ru", "short")

    button = keyboard.inline_keyboard[-1][0]
    assert button.callback_data == CALLBACK_POST_LENGTH
    assert get_string("post_length_short", "ru") in button.text


def test_create_post_keyboard_length_button_reflects_the_chosen_preset():
    short_button = build_create_post_keyboard("", "ru", "short").inline_keyboard[-1][0]
    expanded_button = build_create_post_keyboard("", "ru", "expanded").inline_keyboard[-1][0]

    assert short_button.text != expanded_button.text


def test_post_length_keyboard_has_a_row_per_preset():
    keyboard = build_post_length_keyboard("medium", "ru")

    assert len(keyboard.inline_keyboard) == len(post_length.PRESETS)
    callbacks = [row[0].callback_data for row in keyboard.inline_keyboard]
    assert callbacks == [
        f"{CALLBACK_POST_LENGTH_SET_PREFIX}:short",
        f"{CALLBACK_POST_LENGTH_SET_PREFIX}:medium",
        f"{CALLBACK_POST_LENGTH_SET_PREFIX}:expanded",
    ]


def test_post_length_keyboard_marks_the_current_preset():
    keyboard = build_post_length_keyboard("medium", "ru")

    texts = {row[0].callback_data: row[0].text for row in keyboard.inline_keyboard}
    assert texts[f"{CALLBACK_POST_LENGTH_SET_PREFIX}:medium"].startswith("✓")
    assert not texts[f"{CALLBACK_POST_LENGTH_SET_PREFIX}:short"].startswith("✓")


def test_post_length_keyboard_marks_a_different_preset_when_chosen():
    keyboard = build_post_length_keyboard("expanded", "en")

    texts = {row[0].callback_data: row[0].text for row in keyboard.inline_keyboard}
    assert texts[f"{CALLBACK_POST_LENGTH_SET_PREFIX}:expanded"].startswith("✓")
    assert not texts[f"{CALLBACK_POST_LENGTH_SET_PREFIX}:medium"].startswith("✓")
