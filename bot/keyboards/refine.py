from __future__ import annotations

from typing import Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.locales.loader import get_string

Platform = Literal["telegram", "vk"]

CALLBACK_MORE_PREFIX = "refine:more"
CALLBACK_SHORTEN_PREFIX = "refine:shorten"
CALLBACK_PUBLISH_PREFIX = "refine:publish"


def build_refine_keyboard(platform: Platform, variant_index: int, lang: str) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(
            text=get_string("refine_more_button", lang),
            callback_data=f"{CALLBACK_MORE_PREFIX}:{platform}:{variant_index}",
        ),
        InlineKeyboardButton(
            text=get_string("refine_shorten_button", lang),
            callback_data=f"{CALLBACK_SHORTEN_PREFIX}:{platform}:{variant_index}",
        ),
    ]
    publish_button = [
        InlineKeyboardButton(
            text=get_string("publish_to_channel_button", lang),
            callback_data=f"{CALLBACK_PUBLISH_PREFIX}:{platform}:{variant_index}",
        )
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons, publish_button])
