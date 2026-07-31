from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.keyboards.authorpost import CALLBACK_SAMPLES_DONE
from bot.keyboards.start import CALLBACK_NEWS_DIGEST
from bot.locales.loader import get_string

CALLBACK_OWN_TOPIC = "authorpost:own_topic"


# WHY its own module rather than bot/keyboards/authorpost.py: this keyboard
# mixes a button from authorpost with the digest button from start, and
# start.py already imports from authorpost.py — putting it there would close
# the import cycle. Nothing imports this module back, so the graph stays a DAG.
def build_style_ready_keyboard(lang: str, has_source_text: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    # Only offered when a digest item was picked before the samples were sent
    # (the authored-post flow). Reached from /settov there is no topic yet, and
    # the button would lead straight to an "expired digest" reply.
    if has_source_text:
        rows.append(
            [
                InlineKeyboardButton(
                    text=get_string("authorpost_samples_done_button", lang),
                    callback_data=CALLBACK_SAMPLES_DONE,
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=get_string("style_button_own_topic", lang),
                callback_data=CALLBACK_OWN_TOPIC,
            )
        ]
    )
    # Reuses the main menu's own callback instead of a private one: two entry
    # points into the same digest must not drift apart.
    rows.append(
        [
            InlineKeyboardButton(
                text=get_string("style_button_fresh_digest", lang),
                callback_data=CALLBACK_NEWS_DIGEST,
            )
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)
