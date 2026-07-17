from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers.language import cmd_language, on_language_selected
from bot.keyboards.language import build_language_keyboard
from bot.locales.loader import get_string
from bot.storage.users import get_interface_language, set_interface_language


def _make_message(telegram_id: int):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id)
    return message


def _make_callback(telegram_id: int, language: str):
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=telegram_id)
    callback.data = f"lang:{language}"
    callback.message = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_cmd_language_shows_keyboard(db_path):
    message = _make_message(111)

    await cmd_language(message, db_path)

    message.answer.assert_awaited_once_with(
        get_string("language_prompt", "ru"), reply_markup=build_language_keyboard()
    )


@pytest.mark.asyncio
async def test_cmd_language_prompts_in_current_interface_language(db_path):
    set_interface_language(db_path, 111, "en")
    message = _make_message(111)

    await cmd_language(message, db_path)

    message.answer.assert_awaited_once_with(
        get_string("language_prompt", "en"), reply_markup=build_language_keyboard()
    )


@pytest.mark.asyncio
async def test_language_selection_persists_choice(db_path):
    callback = _make_callback(222, "vi")

    await on_language_selected(callback, db_path)

    assert get_interface_language(db_path, 222) == "vi"


@pytest.mark.asyncio
async def test_language_selection_confirms_in_new_language(db_path):
    callback = _make_callback(222, "zh")

    await on_language_selected(callback, db_path)

    callback.message.answer.assert_awaited_once_with(
        get_string("language_set_confirmation", "zh")
    )
    callback.answer.assert_awaited_once()
