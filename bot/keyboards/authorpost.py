from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.locales.loader import get_string

CALLBACK_START = "authorpost:start"
CALLBACK_ITEM_PREFIX = "authorpost:item"
CALLBACK_NEXT = "authorpost:next"
CALLBACK_USE_SAVED = "authorpost:use_saved"
CALLBACK_NEW_SAMPLES = "authorpost:new_samples"
CALLBACK_SAMPLES_DONE = "authorpost:samples_done"
CALLBACK_PLATFORM_PREFIX = "authorpost:platform"

# Four number buttons per row: Telegram renders inline rows edge-to-edge, and
# a digest tops out at 8 items (4 news + 3 papers + 1 methods summary), so
# this lays out as one or two tidy rows rather than a tall single column.
_ITEMS_PER_ROW = 4


def build_item_choice_keyboard(item_count: int, generation: int) -> InlineKeyboardMarkup:
    # Buttons carry the item's zero-based index, never its title: Telegram
    # caps callback_data at 64 bytes and a news headline blows straight past
    # that. The titles themselves live in FSM data (see
    # bot/handlers/authorpost.py), keyed by this index. The generation is
    # carried alongside the index so a tap on a button from an older, since-
    # overwritten digest can be told apart from one on the current digest —
    # without it, two digests of equal length are indistinguishable and a
    # stale button silently resolves against the wrong topic's items.
    buttons = [
        InlineKeyboardButton(
            text=str(index + 1),
            callback_data=f"{CALLBACK_ITEM_PREFIX}:{generation}:{index}",
        )
        for index in range(item_count)
    ]
    rows = [
        buttons[start : start + _ITEMS_PER_ROW]
        for start in range(0, len(buttons), _ITEMS_PER_ROW)
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_next_step_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("authorpost_next_button", lang),
                    callback_data=CALLBACK_NEXT,
                )
            ]
        ]
    )


def build_saved_examples_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("authorpost_use_saved_button", lang),
                    callback_data=CALLBACK_USE_SAVED,
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_string("authorpost_new_samples_button", lang),
                    callback_data=CALLBACK_NEW_SAMPLES,
                )
            ],
        ]
    )


def build_platform_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_string("authorpost_platform_telegram_button", lang),
                    callback_data=f"{CALLBACK_PLATFORM_PREFIX}:telegram",
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_string("authorpost_platform_vk_button", lang),
                    callback_data=f"{CALLBACK_PLATFORM_PREFIX}:vk",
                )
            ],
            [
                InlineKeyboardButton(
                    text=get_string("authorpost_platform_both_button", lang),
                    callback_data=f"{CALLBACK_PLATFORM_PREFIX}:both",
                )
            ],
        ]
    )
