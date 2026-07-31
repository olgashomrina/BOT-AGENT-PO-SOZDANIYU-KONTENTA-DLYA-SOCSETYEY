from __future__ import annotations

from bot.keyboards.circle import (
    CALLBACK_ADD_DONORS,
    CALLBACK_CONSENT_ACCEPT,
    CALLBACK_DELETE,
    CALLBACK_DELETE_CONFIRM,
    CALLBACK_DONORS_DONE,
    build_consent_keyboard,
    build_delete_confirm_keyboard,
    build_donors_keyboard,
    build_my_double_keyboard,
)


def _callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def test_consent_keyboard_offers_accept():
    assert _callbacks(build_consent_keyboard("ru")) == [CALLBACK_CONSENT_ACCEPT]


def test_donors_keyboard_hides_finish_until_enough_donors():
    assert _callbacks(build_donors_keyboard("ru", can_finish=False)) == []


def test_donors_keyboard_shows_finish_when_enough():
    assert _callbacks(build_donors_keyboard("ru", can_finish=True)) == [
        CALLBACK_DONORS_DONE
    ]


def test_my_double_keyboard_has_add_and_delete():
    callbacks = _callbacks(build_my_double_keyboard("ru"))

    assert CALLBACK_ADD_DONORS in callbacks
    assert CALLBACK_DELETE in callbacks


def test_delete_confirm_keyboard_asks_for_confirmation():
    assert CALLBACK_DELETE_CONFIRM in _callbacks(build_delete_confirm_keyboard("ru"))


def test_callback_data_fits_telegram_limit():
    # Telegram отводит под callback_data 64 байта.
    for value in (
        CALLBACK_CONSENT_ACCEPT,
        CALLBACK_DONORS_DONE,
        CALLBACK_ADD_DONORS,
        CALLBACK_DELETE,
        CALLBACK_DELETE_CONFIRM,
    ):
        assert len(value.encode("utf-8")) <= 64
