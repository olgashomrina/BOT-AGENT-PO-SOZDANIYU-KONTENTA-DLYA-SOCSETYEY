from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.locales.loader import get_string

CALLBACK_CONFIRM = "transcript:confirm"
CALLBACK_EDIT = "transcript:edit"


def build_transcript_confirm_keyboard(lang: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=get_string("transcript_confirm_button", lang), callback_data=CALLBACK_CONFIRM
        ),
        InlineKeyboardButton(
            text=get_string("transcript_edit_button", lang), callback_data=CALLBACK_EDIT
        ),
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])
