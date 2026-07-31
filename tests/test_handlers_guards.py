from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers.guards import check_limit_or_reply, check_message_limit_or_reply
from bot.locales.loader import get_string
from bot.storage.limits import increment_usage

TELEGRAM_ID = 111


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")


def _make_message():
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=TELEGRAM_ID, language_code="ru")
    return message


def _make_callback():
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=TELEGRAM_ID, language_code="ru")
    callback.message = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_message_guard_passes_when_under_the_limit(db_path, monkeypatch):
    monkeypatch.setenv("DAILY_LIMIT", "5")
    message = _make_message()

    assert await check_message_limit_or_reply(message, db_path, "ru") is True
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_guard_reports_the_daily_limit(db_path, monkeypatch):
    monkeypatch.setenv("DAILY_LIMIT", "1")
    increment_usage(db_path, TELEGRAM_ID)
    message = _make_message()

    assert await check_message_limit_or_reply(message, db_path, "ru") is False
    message.answer.assert_awaited_once_with(
        get_string("error_daily_limit_exceeded", "ru")
    )


@pytest.mark.asyncio
async def test_message_guard_reports_the_monthly_limit(db_path, monkeypatch):
    monkeypatch.setenv("DAILY_LIMIT", "50")
    monkeypatch.setenv("MONTHLY_LIMIT", "1")
    increment_usage(db_path, TELEGRAM_ID)
    message = _make_message()

    assert await check_message_limit_or_reply(message, db_path, "en") is False
    message.answer.assert_awaited_once_with(
        get_string("error_monthly_limit_exceeded", "en")
    )


@pytest.mark.asyncio
async def test_callback_guard_still_answers_the_callback_when_blocked(db_path, monkeypatch):
    monkeypatch.setenv("DAILY_LIMIT", "1")
    increment_usage(db_path, TELEGRAM_ID)
    callback = _make_callback()

    assert await check_limit_or_reply(callback, db_path, "ru") is False
    callback.message.answer.assert_awaited_once_with(
        get_string("error_daily_limit_exceeded", "ru")
    )
    callback.answer.assert_awaited_once()
