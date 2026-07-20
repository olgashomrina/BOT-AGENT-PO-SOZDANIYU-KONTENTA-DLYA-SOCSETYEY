from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.locales.loader import get_string

CALLBACK_DONE = "settov:done"


def build_settov_done_keyboard(lang: str) -> InlineKeyboardMarkup:
    button = InlineKeyboardButton(
        text=get_string("settov_done_button", lang), callback_data=CALLBACK_DONE
    )
    return InlineKeyboardMarkup(inline_keyboard=[[button]])
