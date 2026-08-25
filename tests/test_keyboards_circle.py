from __future__ import annotations

from bot.keyboards.circle import (
    CALLBACK_ADD_DONORS,
    CALLBACK_CONSENT_ACCEPT,
    CALLBACK_DELETE,
    CALLBACK_DELETE_CONFIRM,
    CALLBACK_DONORS_DONE,
    CALLBACK_FACE,
    CALLBACK_LOOK_ACTIVATE_PREFIX,
    CALLBACK_LOOK_ADD_PHOTO,
    CALLBACK_LOOK_ADD_PROMPT,
    CALLBACK_LOOK_DELETE_PREFIX,
    CALLBACK_LOOKS,
    CALLBACK_SPEAK,
    CALLBACK_SPEECH_BACK_TO_TEXT,
    CALLBACK_SPEECH_CANCEL,
    CALLBACK_SPEECH_DROP,
    CALLBACK_SPEECH_OTHER_LOOK,
    CALLBACK_SPEECH_PUBLISH,
    CALLBACK_SPEECH_RENDER,
    CALLBACK_SPEECH_RETRY,
    CALLBACK_SPEECH_REVOICE,
    CALLBACK_SPEECH_REWRITE,
    CALLBACK_SPEECH_SCRIPT,
    CALLBACK_SPEECH_TO_LOOK,
    CALLBACK_SPEECH_VOICE_AS_IS,
    CALLBACK_VOICE,
    build_consent_keyboard,
    build_delete_confirm_keyboard,
    build_donors_keyboard,
    build_look_actions_keyboard,
    build_looks_keyboard,
    build_my_double_keyboard,
    build_speech_failed_keyboard,
    build_speech_look_keyboard,
    build_speech_ready_keyboard,
    build_speech_text_keyboard,
    build_speech_voiced_keyboard,
)
from bot.storage.avatar_looks import SOURCE_UPLOADED, Look


def _callbacks(markup) -> list[str]:
    return [button.callback_data for row in markup.inline_keyboard for button in row]


def _labels(markup) -> list[str]:
    return [button.text for row in markup.inline_keyboard for button in row]


def test_consent_keyboard_offers_accept():
    assert _callbacks(build_consent_keyboard("ru")) == [CALLBACK_CONSENT_ACCEPT]


def test_donors_keyboard_hides_finish_until_enough_donors():
    assert _callbacks(build_donors_keyboard("ru", can_finish=False)) == []


def test_donors_keyboard_shows_finish_when_enough():
    assert _callbacks(build_donors_keyboard("ru", can_finish=True)) == [
        CALLBACK_DONORS_DONE
    ]


def test_my_double_keyboard_has_looks_face_voice_and_delete():
    # Экран пересобран под лицо/образы/речь (Task 17): «Добавить кружки»
    # больше не кнопка этого экрана.
    callbacks = _callbacks(build_my_double_keyboard("ru"))

    assert CALLBACK_LOOKS in callbacks
    assert CALLBACK_FACE in callbacks
    assert CALLBACK_VOICE in callbacks
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
        CALLBACK_SPEAK,
        CALLBACK_LOOKS,
        CALLBACK_FACE,
        CALLBACK_VOICE,
        CALLBACK_LOOK_ADD_PHOTO,
        CALLBACK_LOOK_ADD_PROMPT,
        CALLBACK_SPEECH_SCRIPT,
        CALLBACK_SPEECH_VOICE_AS_IS,
        CALLBACK_SPEECH_REWRITE,
        CALLBACK_SPEECH_CANCEL,
        CALLBACK_SPEECH_TO_LOOK,
        CALLBACK_SPEECH_RENDER,
        CALLBACK_SPEECH_REVOICE,
        CALLBACK_SPEECH_BACK_TO_TEXT,
        CALLBACK_SPEECH_OTHER_LOOK,
        CALLBACK_SPEECH_PUBLISH,
        CALLBACK_SPEECH_DROP,
        CALLBACK_SPEECH_RETRY,
        # Префиксные callback'и растут вместе с id образа — проверяем их
        # тоже, на реалистичном (шестизначном) id.
        f"{CALLBACK_LOOK_ACTIVATE_PREFIX}:999999",
        f"{CALLBACK_LOOK_DELETE_PREFIX}:999999",
    ):
        assert len(value.encode("utf-8")) <= 64


def test_callback_constants_have_the_exact_expected_values():
    # Tasks 18/19/20 импортируют эти же символы — опечатка в значении будет
    # самосогласованной и незаметной без теста, который пинит саму строку.
    assert CALLBACK_SPEAK == "double:speak"
    assert CALLBACK_LOOKS == "double:looks"
    assert CALLBACK_FACE == "double:face"
    assert CALLBACK_VOICE == "double:voice"
    assert CALLBACK_LOOK_ADD_PHOTO == "double:look_photo"
    assert CALLBACK_LOOK_ADD_PROMPT == "double:look_prompt"
    assert CALLBACK_LOOK_ACTIVATE_PREFIX == "double:look_on"
    assert CALLBACK_LOOK_DELETE_PREFIX == "double:look_del"
    assert CALLBACK_SPEECH_SCRIPT == "speech:script"
    assert CALLBACK_SPEECH_VOICE_AS_IS == "speech:as_is"
    assert CALLBACK_SPEECH_REWRITE == "speech:rewrite"
    assert CALLBACK_SPEECH_CANCEL == "speech:cancel"
    assert CALLBACK_SPEECH_TO_LOOK == "speech:to_look"
    assert CALLBACK_SPEECH_RENDER == "speech:render"
    assert CALLBACK_SPEECH_REVOICE == "speech:revoice"
    assert CALLBACK_SPEECH_BACK_TO_TEXT == "speech:back"
    assert CALLBACK_SPEECH_OTHER_LOOK == "speech:other_look"
    assert CALLBACK_SPEECH_PUBLISH == "speech:publish"
    assert CALLBACK_SPEECH_DROP == "speech:drop"
    assert CALLBACK_SPEECH_RETRY == "speech:retry"


def test_double_screen_offers_speech_looks_face_and_voice():
    markup = build_my_double_keyboard("ru", has_face=True, has_look=True)

    assert CALLBACK_SPEAK in _callbacks(markup)
    assert CALLBACK_LOOKS in _callbacks(markup)
    assert CALLBACK_FACE in _callbacks(markup)
    assert CALLBACK_VOICE in _callbacks(markup)
    assert CALLBACK_DELETE in _callbacks(markup)


def test_speech_button_is_hidden_until_face_and_look_exist():
    # Кнопка, которая ведёт в отказ, честнее не показываться вовсе.
    without_face = build_my_double_keyboard("ru", has_face=False, has_look=True)
    without_look = build_my_double_keyboard("ru", has_face=True, has_look=False)

    assert CALLBACK_SPEAK not in _callbacks(without_face)
    assert CALLBACK_SPEAK not in _callbacks(without_look)


def test_looks_keyboard_lists_every_look_and_marks_the_active_one():
    looks = [
        Look(id=1, file_id="a", title="студия", source=SOURCE_UPLOADED, prompt=None, is_active=True, created_at="now"),
        Look(id=2, file_id="b", title="улица", source=SOURCE_UPLOADED, prompt=None, is_active=False, created_at="now"),
    ]

    markup = build_looks_keyboard("ru", looks)

    labels = _labels(markup)
    assert any(label.startswith("✓") and "студия" in label for label in labels)
    assert any(label == "улица" for label in labels)
    assert f"{CALLBACK_LOOK_ACTIVATE_PREFIX}:2" in _callbacks(markup)


def test_looks_keyboard_always_offers_both_ways_to_add():
    markup = build_looks_keyboard("ru", [])

    assert CALLBACK_LOOK_ADD_PHOTO in _callbacks(markup)
    assert CALLBACK_LOOK_ADD_PROMPT in _callbacks(markup)


def test_look_actions_hide_activate_for_the_active_look():
    markup = build_look_actions_keyboard("ru", look_id=3, is_active=True)

    assert f"{CALLBACK_LOOK_ACTIVATE_PREFIX}:3" not in _callbacks(markup)
    assert f"{CALLBACK_LOOK_DELETE_PREFIX}:3" in _callbacks(markup)


def test_speech_text_screen_offers_voicing_script_and_cancel():
    markup = build_speech_text_keyboard("ru")

    assert CALLBACK_SPEECH_VOICE_AS_IS in _callbacks(markup)
    assert CALLBACK_SPEECH_SCRIPT in _callbacks(markup)
    assert CALLBACK_SPEECH_REWRITE in _callbacks(markup)
    assert CALLBACK_SPEECH_CANCEL in _callbacks(markup)


def test_voiced_screen_offers_filming_revoicing_and_going_back():
    markup = build_speech_voiced_keyboard("ru")

    # Именно TO_LOOK, а не RENDER: с этого экрана деньги ещё не тратятся.
    assert CALLBACK_SPEECH_TO_LOOK in _callbacks(markup)
    assert CALLBACK_SPEECH_RENDER not in _callbacks(markup)
    assert CALLBACK_SPEECH_REVOICE in _callbacks(markup)
    assert CALLBACK_SPEECH_BACK_TO_TEXT in _callbacks(markup)


def test_other_look_button_hidden_when_there_is_only_one_look():
    single = build_speech_look_keyboard("ru", has_other_looks=False)
    several = build_speech_look_keyboard("ru", has_other_looks=True)

    assert CALLBACK_SPEECH_OTHER_LOOK not in _callbacks(single)
    assert CALLBACK_SPEECH_OTHER_LOOK in _callbacks(several)


def test_ready_screen_hides_publishing_without_a_channel():
    # Канал не привязан — кнопка публикации не показывается, а не отказывает.
    without = build_speech_ready_keyboard("ru", can_publish=False)
    with_channel = build_speech_ready_keyboard("ru", can_publish=True)

    assert CALLBACK_SPEECH_PUBLISH not in _callbacks(without)
    assert CALLBACK_SPEECH_PUBLISH in _callbacks(with_channel)
    assert CALLBACK_SPEECH_DROP in _callbacks(without)


def test_failed_screen_offers_a_retry():
    markup = build_speech_failed_keyboard("ru")

    assert CALLBACK_SPEECH_RETRY in _callbacks(markup)
