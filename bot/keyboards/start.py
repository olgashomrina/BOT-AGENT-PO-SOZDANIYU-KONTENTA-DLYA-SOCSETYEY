from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from bot.keyboards.authorpost import CALLBACK_START as CALLBACK_AUTHORPOST_START
from bot.keyboards.circle import CALLBACK_MY_DOUBLE
from bot.locales.loader import get_string
from bot.services.post_length import PRESETS as _LENGTH_PRESETS

CALLBACK_CAPABILITIES = "menu:capabilities"
CALLBACK_CREATE_POST = "menu:create_post"
CALLBACK_NEWS_DIGEST = "menu:news_digest"
CALLBACK_TEXT_HINT = "menu:text_hint"
CALLBACK_PHOTO_GEN = "menu:photo_gen"
CALLBACK_DIGEST_SET_TOPIC = "menu:digest_set_topic"
CALLBACK_POST_LENGTH = "menu:post_length"
CALLBACK_POST_LENGTH_SET_PREFIX = "menu:post_length:set"


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
            [
                InlineKeyboardButton(
                    text=get_string("menu_news_digest_button", lang),
                    callback_data=CALLBACK_NEWS_DIGEST,
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_string("menu_my_double_button", lang),
                    callback_data=CALLBACK_MY_DOUBLE,
                )
            ],
        ]
    )


def build_create_post_keyboard(
    mini_app_url: str, lang: str, post_length_key: str
) -> InlineKeyboardMarkup:
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
    # Текущее значение стоит прямо в подписи: настройка меняется редко, и без
    # него пользователю пришлось бы открывать экран только чтобы вспомнить,
    # что там выбрано.
    rows.append(
        [
            InlineKeyboardButton(
                text=get_string(
                    "post_length_button",
                    lang,
                    value=get_string(f"post_length_{post_length_key}", lang),
                ),
                callback_data=CALLBACK_POST_LENGTH,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_post_length_keyboard(current_key: str, lang: str) -> InlineKeyboardMarkup:
    rows = []
    for key in _LENGTH_PRESETS:
        label = get_string(f"post_length_{key}", lang)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"✓ {label}" if key == current_key else label,
                    callback_data=f"{CALLBACK_POST_LENGTH_SET_PREFIX}:{key}",
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_digest_topic_keyboard(lang: str, has_saved_topic: bool) -> InlineKeyboardMarkup:
    label_key = (
        "menu_digest_change_topic_button" if has_saved_topic else "menu_digest_write_topic_button"
    )
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string(label_key, lang),
                    callback_data=CALLBACK_DIGEST_SET_TOPIC,
                )
            ],
            # Offered even when the digest turned up empty: the button leads
            # to a "digest expired / collect a fresh one" reply rather than a
            # dead end, and keeping the keyboard shape constant means the
            # user's muscle memory for the button position always holds.
            [
                InlineKeyboardButton(
                    text=get_string("authorpost_button", lang),
                    callback_data=CALLBACK_AUTHORPOST_START,
                )
            ],
        ]
    )
