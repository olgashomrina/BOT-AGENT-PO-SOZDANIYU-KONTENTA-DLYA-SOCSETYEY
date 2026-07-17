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
