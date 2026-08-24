from __future__ import annotations

import pytest

from bot.locales import en, ru, vi, zh
from bot.locales.loader import SUPPORTED_LANGUAGES, get_string

_LOCALE_MODULES = {"ru": ru, "en": en, "vi": vi, "zh": zh}


def test_all_locales_have_identical_keys():
    key_sets = {lang: set(module.STRINGS.keys()) for lang, module in _LOCALE_MODULES.items()}
    reference = key_sets["ru"]
    for lang, keys in key_sets.items():
        assert keys == reference, f"{lang} locale keys differ from ru: {keys ^ reference}"


def test_supported_languages_match_locale_modules():
    assert set(SUPPORTED_LANGUAGES) == set(_LOCALE_MODULES.keys())


@pytest.mark.parametrize("lang", ["ru", "en", "vi", "zh"])
def test_get_string_returns_non_empty_value_for_each_language(lang):
    assert get_string("start_greeting", lang).strip()


def test_get_string_falls_back_to_ru_for_unsupported_language():
    assert get_string("start_greeting", "fr") == ru.STRINGS["start_greeting"]


def test_get_string_falls_back_to_ru_for_missing_key(monkeypatch):
    monkeypatch.delitem(en.STRINGS, "start_greeting")

    assert get_string("start_greeting", "en") == ru.STRINGS["start_greeting"]


def test_get_string_formats_placeholders(monkeypatch):
    monkeypatch.setitem(ru.STRINGS, "start_greeting", "Привет, {name}!")

    assert get_string("start_greeting", "ru", name="Аня") == "Привет, Аня!"


_TALKING_DOUBLE_KEYS = (
    "double_status_full",
    "double_face_present",
    "double_face_missing",
    "double_look_none",
    "double_speak_button",
    "double_looks_button",
    "double_face_button",
    "double_voice_button",
    "face_invite",
    "face_saved",
    "face_expected_photo",
    "looks_title",
    "looks_add_photo_button",
    "looks_add_prompt_button",
    "looks_upload_invite",
    "looks_prompt_invite",
    "looks_hair_warning",
    "looks_need_face",
    "looks_building",
    "looks_failed",
    "looks_saved",
    "looks_activated",
    "look_activate_button",
    "look_delete_button",
    "look_deleted",
    "speech_invite",
    "speech_text_received",
    "speech_voice_as_is_button",
    "speech_script_button",
    "speech_rewrite_button",
    "speech_cancel_button",
    "speech_cancelled",
    "speech_script_failed",
    "speech_prompter",
    "speech_voice_failed",
    "speech_voiced",
    "speech_render_button",
    "speech_revoice_button",
    "speech_back_to_text_button",
    "speech_too_long",
    "speech_look_screen",
    "speech_render_with_look_button",
    "speech_other_look_button",
    "speech_rendering",
    "speech_ready",
    "speech_rewrite_text_button",
    "speech_drop_button",
    "speech_failed",
    "speech_retry_button",
    "speech_limit_exceeded",
    "speech_need_face",
    "speech_need_look",
    "speech_expected_input",
)


@pytest.mark.parametrize("key", _TALKING_DOUBLE_KEYS)
@pytest.mark.parametrize("lang", ["ru", "en", "vi", "zh"])
def test_talking_double_strings_exist_in_every_language(key, lang):
    assert _LOCALE_MODULES[lang].STRINGS.get(key, "").strip()


def test_placeholder_keys_accept_their_arguments():
    # Опечатка в имени подстановки видна только в момент показа экрана —
    # то есть у пользователя. Проверяем здесь.
    assert get_string(
        "double_status_full", "ru", face="есть", looks=3, active="студия"
    )
    assert get_string("looks_title", "ru", count=3, active="студия")
    assert get_string("speech_text_received", "ru", text="привет")
    assert get_string("speech_voiced", "ru", seconds=28)
    assert get_string("speech_too_long", "ru", limit=60)
    assert get_string("speech_limit_exceeded", "ru", left=0)
    assert get_string("speech_look_screen", "ru", title="студия")
