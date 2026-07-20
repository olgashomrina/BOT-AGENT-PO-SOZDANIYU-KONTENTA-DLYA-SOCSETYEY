from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.handlers.content import _resolve_language
from bot.keyboards.settov import CALLBACK_DONE, build_settov_done_keyboard
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.storage.style_examples import add_style_example, get_style_examples

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="settov")

# Plan.md Phase 14: "validate/reject absurdly long input at the point of
# collection" — kept here (not in storage) so bot/storage/style_examples.py
# never has to deal with pathological input at all.
MAX_EXAMPLE_LENGTH = 2000


class SettovStates(StatesGroup):
    collecting_examples = State()


@router.message(Command("settov"))
async def cmd_settov(message: Message, db_path: str, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    await state.set_state(SettovStates.collecting_examples)
    await message.answer(
        get_string("settov_instructions", language),
        reply_markup=build_settov_done_keyboard(language),
    )


@router.message(SettovStates.collecting_examples)
async def on_settov_example(message: Message, db_path: str) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    if not message.text:
        await message.answer(
            get_string("settov_non_text_reprompt", language),
            reply_markup=build_settov_done_keyboard(language),
        )
        return

    if len(message.text) > MAX_EXAMPLE_LENGTH:
        await message.answer(
            get_string("settov_example_too_long", language),
            reply_markup=build_settov_done_keyboard(language),
        )
        return

    add_style_example(db_path, telegram_id, message.text)
    await message.answer(
        get_string("settov_example_saved", language),
        reply_markup=build_settov_done_keyboard(language),
    )
    logger.info(
        "Style example saved",
        extra={"user_id": telegram_id, "operation": "handler:settov"},
    )


# WHY no whitelist re-check here (unlike bot/handlers/refine.py's callbacks):
# the only way to reach this callback is to have first been let through
# WhitelistMiddleware to run /settov and send example messages (both plain
# Message events, gated by dispatcher.message.outer_middleware in
# bot/main.py) — this button never triggers an AI Gateway call and never
# consumes usage quota, so even a user whose access was revoked in the
# narrow window between sending examples and tapping "Done" only gets a
# harmless local confirmation, unlike refine's buttons which spend quota.
@router.callback_query(F.data == CALLBACK_DONE, SettovStates.collecting_examples)
async def on_settov_done(callback: CallbackQuery, db_path: str, state: FSMContext) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    await state.set_state(None)
    count = len(get_style_examples(db_path, telegram_id))
    await callback.message.answer(
        get_string("settov_finished_confirmation", language, count=count)
    )
    await callback.answer()
    logger.info(
        "Style example collection finished",
        extra={
            "user_id": telegram_id,
            "operation": "handler:settov",
            "example_count": count,
        },
    )
