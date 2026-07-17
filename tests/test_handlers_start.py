from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers.start import cmd_help, cmd_start
from bot.locales.loader import get_string
from bot.storage.users import get_interface_language, set_interface_language


def _make_message(telegram_id: int, language_code: str | None):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code=language_code)
    return message


@pytest.mark.asyncio
async def test_new_user_gets_language_from_supported_language_code(db_path):
    message = _make_message(111, "vi")

    await cmd_start(message, db_path)

    assert get_interface_language(db_path, 111) == "vi"
    message.answer.assert_awaited_once_with(get_string("start_greeting", "vi"))


@pytest.mark.asyncio
async def test_new_user_defaults_to_ru_for_unsupported_language_code(db_path):
    message = _make_message(222, "fr")

    await cmd_start(message, db_path)

    assert get_interface_language(db_path, 222) == "ru"
    message.answer.assert_awaited_once_with(get_string("start_greeting", "ru"))


@pytest.mark.asyncio
async def test_new_user_defaults_to_ru_when_language_code_missing(db_path):
    message = _make_message(333, None)

    await cmd_start(message, db_path)

    assert get_interface_language(db_path, 333) == "ru"


@pytest.mark.asyncio
async def test_existing_user_keeps_stored_language_on_start(db_path):
    set_interface_language(db_path, 444, "en")
    message = _make_message(444, "vi")

    await cmd_start(message, db_path)

    assert get_interface_language(db_path, 444) == "en"
    message.answer.assert_awaited_once_with(get_string("start_greeting", "en"))


@pytest.mark.asyncio
async def test_help_replies_in_default_language_for_new_user(db_path):
    message = _make_message(555, "ru")

    await cmd_help(message, db_path)

    message.answer.assert_awaited_once_with(get_string("help_text", "ru"))


@pytest.mark.asyncio
async def test_help_replies_in_stored_interface_language(db_path):
    set_interface_language(db_path, 666, "zh")
    message = _make_message(666, "en")

    await cmd_help(message, db_path)

    message.answer.assert_awaited_once_with(get_string("help_text", "zh"))
