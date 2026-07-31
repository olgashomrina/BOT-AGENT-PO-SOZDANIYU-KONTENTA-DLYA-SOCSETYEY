from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.locales.loader import get_string

CALLBACK_MY_DOUBLE = "menu:my_double"
CALLBACK_CONSENT_ACCEPT = "circle:consent_ok"
CALLBACK_DONORS_DONE = "circle:donors_done"
CALLBACK_ADD_DONORS = "circle:add_donors"
CALLBACK_DELETE = "circle:delete"
CALLBACK_DELETE_CONFIRM = "circle:delete_confirm"


def build_consent_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("double_consent_accept_button", lang),
                    callback_data=CALLBACK_CONSENT_ACCEPT,
                )
            ]
        ]
    )


def build_donors_keyboard(lang: str, can_finish: bool) -> InlineKeyboardMarkup:
    # Кнопку «Готово» показываем только когда доноров хватает: иначе она
    # обещает результат, которого сценарий выдать не может.
    rows: list[list[InlineKeyboardButton]] = []
    if can_finish:
        rows.append(
            [
                InlineKeyboardButton(
                    text=get_string("double_donors_done_button", lang),
                    callback_data=CALLBACK_DONORS_DONE,
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_my_double_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("double_add_donors_button", lang),
                    callback_data=CALLBACK_ADD_DONORS,
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_string("double_delete_button", lang),
                    callback_data=CALLBACK_DELETE,
                )
            ],
        ]
    )


def build_delete_confirm_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("double_delete_confirm_button", lang),
                    callback_data=CALLBACK_DELETE_CONFIRM,
                )
            ]
        ]
    )
