from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.locales.loader import SUPPORTED_LANGUAGES

CALLBACK_PREFIX = "lang:"

_LANGUAGE_LABELS = {
    "ru": "Русский",
    "en": "English",
    "vi": "Tiếng Việt",
    "zh": "中文",
}


def build_language_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=_LANGUAGE_LABELS[lang], callback_data=f"{CALLBACK_PREFIX}{lang}"
        )
        for lang in SUPPORTED_LANGUAGES
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])
