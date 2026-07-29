from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery

from bot.handlers.content import _resolve_language
from bot.handlers.refine import _check_whitelist_or_reply, _safe_answer
from bot.keyboards.authorpost import (
    CALLBACK_ITEM_PREFIX,
    CALLBACK_START,
    build_item_choice_keyboard,
    build_next_step_keyboard,
)
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="authorpost")

# Below this many stored style examples the bot refuses to write: fewer
# samples do not carry a recognisable voice, they just bias the model toward
# whichever single post it saw.
REQUIRED_EXAMPLES = 5


class AuthorPostStates(StatesGroup):
    # Only one state, and only for the sample-collection step, which is the
    # one place this flow has to intercept ordinary text messages. Every
    # other step is a callback_query with unique callback_data. A state left
    # set outside this step would be actively harmful: route_content in
    # bot/handlers/content.py filters on StateFilter(None), so the bot would
    # stop reacting to normal messages entirely.
    collecting_examples = State()


async def _report_expired_digest(callback: CallbackQuery, language: str) -> None:
    # Reached when FSM data has no digest items — most often because the bot
    # process restarted (storage is in-memory MemoryStorage, see
    # bot/main.py), but also when a button from a previous digest is tapped
    # after a newer, shorter digest replaced the list.
    await callback.message.answer(get_string("authorpost_digest_expired", language))
    await _safe_answer(callback)


@router.callback_query(F.data == CALLBACK_START)
async def on_authorpost_start(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    data = await state.get_data()
    items = data.get("digest_items") or []
    if not items:
        await _report_expired_digest(callback, language)
        return

    await callback.message.answer(
        get_string("authorpost_choose_item", language),
        reply_markup=build_item_choice_keyboard(len(items)),
    )
    await _safe_answer(callback)


@router.callback_query(F.data.startswith(f"{CALLBACK_ITEM_PREFIX}:"))
async def on_authorpost_item(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    data = await state.get_data()
    items = data.get("digest_items") or []
    # callback.data is client-supplied: a modified client can send any string
    # matching the startswith filter above, not just the indices this bot's
    # own keyboard emitted via range(len(items)). So the index is both parsed
    # defensively and bounds-checked on both ends here, rather than trusted
    # to match the keyboard the bot sent — a non-integer would otherwise raise
    # past _safe_answer and leave the button's spinner hanging, and a negative
    # value would otherwise silently select the last item via Python's
    # negative indexing instead of the one the user actually asked for.
    try:
        index = int(callback.data.rsplit(":", 1)[1])
    except ValueError:
        await _report_expired_digest(callback, language)
        return
    if not 0 <= index < len(items):
        await _report_expired_digest(callback, language)
        return

    item = items[index]
    # source_text is the same FSM key bot/handlers/refine.py reads, so the
    # "Ещё / Короче" buttons under the generated variants work with no extra
    # wiring on this side.
    await state.update_data(source_text=item)
    logger.info(
        "Authored post source selected",
        extra={"user_id": telegram_id, "operation": "handler:authorpost", "item_index": index},
    )

    await callback.message.answer(
        get_string("authorpost_item_chosen", language, item=item),
        reply_markup=build_next_step_keyboard(language),
    )
    await _safe_answer(callback)
