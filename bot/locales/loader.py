from __future__ import annotations

from bot.locales import en, ru, vi, zh

DEFAULT_LANGUAGE = "ru"

_LOCALES = {
    "ru": ru.STRINGS,
    "en": en.STRINGS,
    "vi": vi.STRINGS,
    "zh": zh.STRINGS,
}

SUPPORTED_LANGUAGES = tuple(_LOCALES.keys())


def get_string(key: str, lang: str, **kwargs) -> str:
    locale = _LOCALES.get(lang, _LOCALES[DEFAULT_LANGUAGE])
    template = locale.get(key, _LOCALES[DEFAULT_LANGUAGE][key])
    return template.format(**kwargs) if kwargs else template
