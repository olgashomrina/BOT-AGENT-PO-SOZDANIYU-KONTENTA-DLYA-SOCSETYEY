from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.settov import (
    MAX_EXAMPLE_LENGTH,
    SettovStates,
    cmd_settov,
    on_settov_done,
    on_settov_example,
)
from bot.keyboards.settov import CALLBACK_DONE
from bot.locales.loader import get_string
from bot.storage.style_examples import MAX_EXAMPLES_PER_USER, get_style_examples

TELEGRAM_ID = 111


def _make_state(telegram_id: int = TELEGRAM_ID) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=telegram_id, user_id=telegram_id)
    return FSMContext(storage=storage, key=key)


def _make_message(
    telegram_id: int = TELEGRAM_ID, text: str | None = None, voice=None
):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    message.text = text
    message.voice = voice
    return message


def _make_callback(telegram_id: int = TELEGRAM_ID, data: str = CALLBACK_DONE):
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    callback.data = data
    callback.message = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_cmd_settov_shows_instructions_with_done_button_and_sets_state(db_path):
    message = _make_message()
    state = _make_state()

    await cmd_settov(message, db_path, state)

    message.answer.assert_awaited_once()
    args, kwargs = message.answer.call_args
    assert args[0] == get_string("settov_instructions", "ru")
    assert "reply_markup" in kwargs
    assert await state.get_state() == SettovStates.collecting_examples.state


@pytest.mark.asyncio
async def test_sending_one_example_saves_it_and_reprompts(db_path):
    state = _make_state()
    await state.set_state(SettovStates.collecting_examples)
    message = _make_message(text="Мой старый пост про кофе.")

    await on_settov_example(message, db_path)

    assert get_style_examples(db_path, TELEGRAM_ID) == ["Мой старый пост про кофе."]
    message.answer.assert_awaited_once()
    args, kwargs = message.answer.call_args
    assert args[0] == get_string("settov_example_saved", "ru")
    assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_sending_multiple_examples_in_a_row_all_get_saved(db_path):
    state = _make_state()
    await state.set_state(SettovStates.collecting_examples)

    for text in ["Пост 1", "Пост 2", "Пост 3"]:
        await on_settov_example(_make_message(text=text), db_path)

    assert get_style_examples(db_path, TELEGRAM_ID) == ["Пост 3", "Пост 2", "Пост 1"]


@pytest.mark.asyncio
async def test_sending_more_than_cap_examples_still_saves_up_to_cap(db_path):
    state = _make_state()
    await state.set_state(SettovStates.collecting_examples)

    for index in range(MAX_EXAMPLES_PER_USER + 2):
        await on_settov_example(_make_message(text=f"Пост {index}"), db_path)

    assert len(get_style_examples(db_path, TELEGRAM_ID, limit=100)) == MAX_EXAMPLES_PER_USER


@pytest.mark.asyncio
async def test_overlength_example_is_rejected_and_not_saved(db_path):
    state = _make_state()
    await state.set_state(SettovStates.collecting_examples)
    message = _make_message(text="a" * (MAX_EXAMPLE_LENGTH + 1))

    await on_settov_example(message, db_path)

    assert get_style_examples(db_path, TELEGRAM_ID) == []
    message.answer.assert_awaited_once()
    args, kwargs = message.answer.call_args
    assert args[0] == get_string("settov_example_too_long", "ru")
    assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_non_text_message_is_ignored_with_friendly_reprompt(db_path):
    state = _make_state()
    await state.set_state(SettovStates.collecting_examples)
    message = _make_message(voice=SimpleNamespace(file_id="abc"))

    await on_settov_example(message, db_path)

    assert get_style_examples(db_path, TELEGRAM_ID) == []
    message.answer.assert_awaited_once()
    args, kwargs = message.answer.call_args
    assert args[0] == get_string("settov_non_text_reprompt", "ru")
    assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_done_button_ends_state_and_confirms_with_count(db_path):
    state = _make_state()
    await state.set_state(SettovStates.collecting_examples)
    await on_settov_example(_make_message(text="Пост 1"), db_path)
    await on_settov_example(_make_message(text="Пост 2"), db_path)

    callback = _make_callback()
    await on_settov_done(callback, db_path, state)

    assert await state.get_state() is None
    callback.message.answer.assert_awaited_once_with(
        get_string("settov_finished_confirmation", "ru", count=2)
    )
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_done_button_with_zero_examples_confirms_with_zero_count(db_path):
    state = _make_state()
    await state.set_state(SettovStates.collecting_examples)

    callback = _make_callback()
    await on_settov_done(callback, db_path, state)

    callback.message.answer.assert_awaited_once_with(
        get_string("settov_finished_confirmation", "ru", count=0)
    )
