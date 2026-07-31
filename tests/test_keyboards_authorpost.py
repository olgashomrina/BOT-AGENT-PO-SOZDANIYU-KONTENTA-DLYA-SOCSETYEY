from __future__ import annotations

from bot.keyboards.authorpost import (
    CALLBACK_ITEM_PREFIX,
    CALLBACK_NEW_SAMPLES,
    CALLBACK_NEXT,
    CALLBACK_PLATFORM_PREFIX,
    CALLBACK_SAMPLES_DONE,
    CALLBACK_USE_SAVED,
    build_item_choice_keyboard,
    build_next_step_keyboard,
    build_platform_keyboard,
    build_saved_examples_keyboard,
)
from bot.locales.loader import get_string


def test_item_choice_keyboard_has_one_button_per_item():
    keyboard = build_item_choice_keyboard(6, 1)

    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert len(buttons) == 6
    assert [button.text for button in buttons] == ["1", "2", "3", "4", "5", "6"]


def test_item_choice_keyboard_uses_zero_based_index_in_callback_data():
    keyboard = build_item_choice_keyboard(3, 1)

    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [button.callback_data for button in buttons] == [
        f"{CALLBACK_ITEM_PREFIX}:1:0",
        f"{CALLBACK_ITEM_PREFIX}:1:1",
        f"{CALLBACK_ITEM_PREFIX}:1:2",
    ]


def test_item_choice_keyboard_emits_generation_in_every_button():
    # The generation has to survive on every button, not just the first: a
    # forged or mistyped tap on any of them must be checkable against the
    # digest that produced this exact keyboard.
    keyboard = build_item_choice_keyboard(5, 7)

    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [button.callback_data for button in buttons] == [
        f"{CALLBACK_ITEM_PREFIX}:7:{index}" for index in range(5)
    ]


def test_item_choice_keyboard_wraps_at_four_per_row():
    keyboard = build_item_choice_keyboard(8, 1)

    assert len(keyboard.inline_keyboard) == 2
    assert len(keyboard.inline_keyboard[0]) == 4
    assert len(keyboard.inline_keyboard[1]) == 4


def test_item_choice_keyboard_partial_last_row():
    keyboard = build_item_choice_keyboard(5, 1)

    assert len(keyboard.inline_keyboard) == 2
    assert len(keyboard.inline_keyboard[1]) == 1


def test_item_choice_keyboard_is_empty_for_zero_items():
    keyboard = build_item_choice_keyboard(0, 1)

    assert keyboard.inline_keyboard == []


def test_next_step_keyboard():
    keyboard = build_next_step_keyboard("en")

    assert keyboard.inline_keyboard[0][0].text == get_string("authorpost_next_button", "en")
    assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_NEXT


def test_saved_examples_keyboard_offers_both_branches():
    keyboard = build_saved_examples_keyboard("ru")

    assert keyboard.inline_keyboard[0][0].text == get_string("authorpost_use_saved_button", "ru")
    assert keyboard.inline_keyboard[0][0].callback_data == CALLBACK_USE_SAVED
    assert keyboard.inline_keyboard[1][0].text == get_string(
        "authorpost_new_samples_button", "ru"
    )
    assert keyboard.inline_keyboard[1][0].callback_data == CALLBACK_NEW_SAMPLES


def test_platform_keyboard_has_three_choices():
    keyboard = build_platform_keyboard("ru")

    buttons = [button for row in keyboard.inline_keyboard for button in row]
    assert [button.callback_data for button in buttons] == [
        f"{CALLBACK_PLATFORM_PREFIX}:telegram",
        f"{CALLBACK_PLATFORM_PREFIX}:vk",
        f"{CALLBACK_PLATFORM_PREFIX}:both",
    ]
    assert buttons[0].text == get_string("authorpost_platform_telegram_button", "ru")
    assert buttons[1].text == get_string("authorpost_platform_vk_button", "ru")
    assert buttons[2].text == get_string("authorpost_platform_both_button", "ru")
