from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from bot.locales.loader import get_string

CALLBACK_CAPABILITIES = "menu:capabilities"
CALLBACK_CREATE_POST = "menu:create_post"
CALLBACK_TEXT_HINT = "menu:text_hint"
CALLBACK_PHOTO_GEN = "menu:photo_gen"


def build_persistent_start_keyboard(lang: str) -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=get_string("start_button_label", lang))]],
        resize_keyboard=True,
    )


def build_start_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("menu_capabilities_button", lang),
                    callback_data=CALLBACK_CAPABILITIES,
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_string("menu_cta_button", lang),
                    callback_data=CALLBACK_CREATE_POST,
                )
            ],
        ]
    )


def build_create_post_keyboard(mini_app_url: str, lang: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if mini_app_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text=get_string("open_site_button", lang),
                    web_app=WebAppInfo(url=mini_app_url),
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=get_string("menu_text_generation_button", lang),
                callback_data=CALLBACK_TEXT_HINT,
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=get_string("menu_photo_generation_button", lang),
                callback_data=CALLBACK_PHOTO_GEN,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
