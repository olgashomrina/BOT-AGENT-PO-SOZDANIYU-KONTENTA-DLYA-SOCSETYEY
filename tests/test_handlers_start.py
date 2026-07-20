from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, call

import pytest

from bot.handlers.start import cmd_help, cmd_start
from bot.locales.loader import get_string
from bot.storage.users import (
    get_interface_language,
    get_onboarding_shown,
    set_interface_language,
    set_onboarding_shown,
)


def _make_message(telegram_id: int, language_code: str | None):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code=language_code)
    return message


def _onboarding_calls(language: str):
    return [
        call(get_string("onboarding_capabilities", language)),
        call(get_string("onboarding_settov", language)),
        call(get_string("onboarding_quick_start", language)),
    ]


@pytest.mark.asyncio
async def test_new_user_gets_language_from_supported_language_code(db_path):
    message = _make_message(111, "vi")

    await cmd_start(message, db_path)

    assert get_interface_language(db_path, 111) == "vi"
    message.answer.assert_has_calls(
        [call(get_string("start_greeting", "vi")), *_onboarding_calls("vi")]
    )


@pytest.mark.asyncio
async def test_new_user_defaults_to_ru_for_unsupported_language_code(db_path):
    message = _make_message(222, "fr")

    await cmd_start(message, db_path)

    assert get_interface_language(db_path, 222) == "ru"
    message.answer.assert_has_calls(
        [call(get_string("start_greeting", "ru")), *_onboarding_calls("ru")]
    )


@pytest.mark.asyncio
async def test_new_user_defaults_to_ru_when_language_code_missing(db_path):
    message = _make_message(333, None)

    await cmd_start(message, db_path)

    assert get_interface_language(db_path, 333) == "ru"


@pytest.mark.asyncio
async def test_new_user_sees_greeting_plus_all_three_onboarding_messages(db_path):
    message = _make_message(777, "ru")

    await cmd_start(message, db_path)

    assert message.answer.await_count == 4
    message.answer.assert_has_calls(
        [call(get_string("start_greeting", "ru")), *_onboarding_calls("ru")]
    )


@pytest.mark.asyncio
async def test_new_user_start_persists_onboarding_shown_flag(db_path):
    message = _make_message(888, "ru")

    await cmd_start(message, db_path)

    assert get_onboarding_shown(db_path, 888) is True


@pytest.mark.asyncio
async def test_second_start_from_same_new_user_does_not_repeat_onboarding(db_path):
    message = _make_message(999, "ru")

    await cmd_start(message, db_path)
    message.answer.reset_mock()
    await cmd_start(message, db_path)

    message.answer.assert_awaited_once_with(get_string("start_greeting", "ru"))


@pytest.mark.asyncio
async def test_returning_user_start_shows_only_greeting(db_path):
    set_interface_language(db_path, 444, "en")
    set_onboarding_shown(db_path, 444, True)
    message = _make_message(444, "vi")

    await cmd_start(message, db_path)

    assert get_interface_language(db_path, 444) == "en"
    message.answer.assert_awaited_once_with(get_string("start_greeting", "en"))


@pytest.mark.asyncio
async def test_help_shows_onboarding_for_new_user(db_path):
    message = _make_message(555, "ru")

    await cmd_help(message, db_path)

    assert message.answer.await_count == 3
    message.answer.assert_has_calls(_onboarding_calls("ru"))


@pytest.mark.asyncio
async def test_help_shows_onboarding_again_for_user_who_already_saw_it(db_path):
    set_interface_language(db_path, 666, "zh")
    set_onboarding_shown(db_path, 666, True)
    message = _make_message(666, "en")

    await cmd_help(message, db_path)

    assert message.answer.await_count == 3
    message.answer.assert_has_calls(_onboarding_calls("zh"))
