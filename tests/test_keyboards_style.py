from __future__ import annotations

from bot.keyboards.authorpost import CALLBACK_SAMPLES_DONE
from bot.keyboards.start import CALLBACK_NEWS_DIGEST
from bot.keyboards.style import CALLBACK_OWN_TOPIC, build_style_ready_keyboard
from bot.locales.loader import get_string


def _callbacks(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_three_buttons_when_a_topic_is_already_chosen():
    markup = build_style_ready_keyboard("ru", has_source_text=True)

    assert _callbacks(markup) == [
        CALLBACK_SAMPLES_DONE,
        CALLBACK_OWN_TOPIC,
        CALLBACK_NEWS_DIGEST,
    ]


def test_two_buttons_when_no_topic_is_chosen():
    markup = build_style_ready_keyboard("ru", has_source_text=False)

    assert _callbacks(markup) == [CALLBACK_OWN_TOPIC, CALLBACK_NEWS_DIGEST]


def test_buttons_are_labelled_from_the_locale():
    markup = build_style_ready_keyboard("en", has_source_text=True)
    labels = [button.text for row in markup.inline_keyboard for button in row]

    assert labels == [
        get_string("authorpost_samples_done_button", "en"),
        get_string("style_button_own_topic", "en"),
        get_string("style_button_fresh_digest", "en"),
    ]


def test_every_button_sits_on_its_own_row():
    markup = build_style_ready_keyboard("ru", has_source_text=True)

    assert all(len(row) == 1 for row in markup.inline_keyboard)
