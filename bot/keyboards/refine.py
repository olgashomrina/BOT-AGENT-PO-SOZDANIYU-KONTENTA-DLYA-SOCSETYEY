from __future__ import annotations

from typing import Literal

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.locales.loader import get_string

Platform = Literal["telegram", "vk"]

CALLBACK_MORE_PREFIX = "refine:more"
CALLBACK_SHORTEN_PREFIX = "refine:shorten"
CALLBACK_PUBLISH_PREFIX = "refine:publish"
CALLBACK_IMAGE_PREFIX = "refine:image"
CALLBACK_SITE_PUSH_PREFIX = "site:push"
CALLBACK_IMAGE_UPGRADE = "img:upgrade"
CALLBACK_IMAGE_UPGRADE_DONE = "img:upgrade:done"
CALLBACK_PACKAGE_PREFIX = "refine:package"


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
    image_button = [
        InlineKeyboardButton(
            text=get_string("generate_image_button", lang),
            callback_data=f"{CALLBACK_IMAGE_PREFIX}:{platform}:{variant_index}",
        )
    ]
    site_push_button = [
        InlineKeyboardButton(
            text=get_string("site_push_button", lang),
            callback_data=f"{CALLBACK_SITE_PUSH_PREFIX}:{platform}:{variant_index}",
        )
    ]
    # "Пакет для соцсетей" сознательно стоит рядом с «Опубликовать в канал», а
    # не вместо неё: публикация в Telegram остаётся автоматической, а внешние
    # площадки — ручными (socseti.md). Кнопка одна на все три площадки, потому
    # что пакет всегда собирается сразу под все — выбирать нечего.
    package_button = [
        InlineKeyboardButton(
            text=get_string("package_button", lang),
            callback_data=f"{CALLBACK_PACKAGE_PREFIX}:{platform}:{variant_index}",
        )
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[buttons, publish_button, image_button, site_push_button, package_button]
    )


def build_image_upgrade_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("image_upgrade_button", lang),
                    callback_data=CALLBACK_IMAGE_UPGRADE,
                )
            ]
        ]
    )


def build_image_upgraded_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("image_upgraded_button", lang),
                    callback_data=CALLBACK_IMAGE_UPGRADE_DONE,
                )
            ]
        ]
    )
