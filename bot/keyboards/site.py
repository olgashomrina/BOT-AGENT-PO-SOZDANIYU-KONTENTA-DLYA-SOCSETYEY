from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from bot.locales.loader import get_string

CALLBACK_PULL_PREFIX = "site:pull"
PILOT_PAGE = "services"
PILOT_BLOCK = "card_1"


def build_site_menu_keyboard(mini_app_url: str, lang: str) -> InlineKeyboardMarkup:
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
                text=get_string("pull_from_site_button", lang),
                callback_data=f"{CALLBACK_PULL_PREFIX}:{PILOT_PAGE}:{PILOT_BLOCK}",
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
