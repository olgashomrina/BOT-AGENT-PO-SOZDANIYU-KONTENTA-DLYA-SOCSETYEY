from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.locales.loader import get_string
from bot.middlewares.rate_limit_middleware import RateLimitMiddleware
from bot.storage.limits import get_daily_count
from bot.storage.users import set_interface_language


def _make_message(telegram_id: int, language_code: str | None = None):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code=language_code)
    return message


@pytest.mark.asyncio
async def test_under_limit_reaches_handler_and_increments_usage(db_path):
    message = _make_message(111)
    handler = AsyncMock(return_value="handled")
    middleware = RateLimitMiddleware(daily_limit=5, monthly_limit=50)

    result = await middleware(handler, message, {"db_path": db_path})

    handler.assert_awaited_once_with(message, {"db_path": db_path})
    assert result == "handled"
    assert get_daily_count(db_path, 111) == 1
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_at_daily_limit_is_blocked_with_friendly_message(db_path):
    message = _make_message(111, "en")
    middleware = RateLimitMiddleware(daily_limit=1, monthly_limit=50)
    handler = AsyncMock()
    await middleware(handler, message, {"db_path": db_path})
    handler.reset_mock()
    message.answer.reset_mock()

    result = await middleware(handler, message, {"db_path": db_path})

    handler.assert_not_awaited()
    message.answer.assert_awaited_once_with(get_string("error_limit_exceeded", "en"))
    assert result is None
    assert get_daily_count(db_path, 111) == 1


@pytest.mark.asyncio
async def test_over_monthly_limit_is_blocked(db_path):
    message = _make_message(111)
    middleware = RateLimitMiddleware(daily_limit=50, monthly_limit=1)
    handler = AsyncMock()
    await middleware(handler, message, {"db_path": db_path})
    handler.reset_mock()

    result = await middleware(handler, message, {"db_path": db_path})

    handler.assert_not_awaited()
    assert result is None


@pytest.mark.asyncio
async def test_blocked_user_uses_stored_interface_language(db_path):
    set_interface_language(db_path, 222, "vi")
    message = _make_message(222, "en")
    middleware = RateLimitMiddleware(daily_limit=0, monthly_limit=50)
    handler = AsyncMock()

    await middleware(handler, message, {"db_path": db_path})

    message.answer.assert_awaited_once_with(get_string("error_limit_exceeded", "vi"))
