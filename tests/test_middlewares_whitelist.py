from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.locales.loader import get_string
from bot.middlewares.whitelist_middleware import WhitelistMiddleware
from bot.storage.users import set_interface_language
from bot.storage.whitelist import add_user


def _make_message(telegram_id: int, language_code: str | None = None):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code=language_code)
    return message


@pytest.mark.asyncio
async def test_whitelisted_user_reaches_handler(db_path):
    add_user(db_path, 111)
    message = _make_message(111)
    handler = AsyncMock(return_value="handled")
    middleware = WhitelistMiddleware()

    result = await middleware(handler, message, {"db_path": db_path})

    handler.assert_awaited_once_with(message, {"db_path": db_path})
    assert result == "handled"
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_non_whitelisted_user_is_blocked_with_friendly_message(db_path):
    message = _make_message(222, "en")
    handler = AsyncMock()
    middleware = WhitelistMiddleware()

    result = await middleware(handler, message, {"db_path": db_path})

    handler.assert_not_awaited()
    message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "en"))
    assert result is None


@pytest.mark.asyncio
async def test_non_whitelisted_user_uses_stored_interface_language(db_path):
    set_interface_language(db_path, 333, "zh")
    message = _make_message(333, "en")
    handler = AsyncMock()
    middleware = WhitelistMiddleware()

    await middleware(handler, message, {"db_path": db_path})

    message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "zh"))


@pytest.mark.asyncio
async def test_non_whitelisted_user_defaults_to_ru_for_unsupported_language_code(db_path):
    message = _make_message(444, "fr")
    handler = AsyncMock()
    middleware = WhitelistMiddleware()

    await middleware(handler, message, {"db_path": db_path})

    message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))
