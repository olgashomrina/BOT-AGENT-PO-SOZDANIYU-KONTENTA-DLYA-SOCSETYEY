from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.authorpost import on_authorpost_item, on_authorpost_start
from bot.keyboards.authorpost import CALLBACK_ITEM_PREFIX, CALLBACK_START
from bot.locales.loader import get_string
from bot.storage.whitelist import add_user

TELEGRAM_ID = 111

DIGEST_ITEMS = [
    "Новость про ИИ",
    "Вторая новость",
    "Научная статья",
    "Новая методика X.",
]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")


@pytest.fixture(autouse=True)
def _whitelisted(db_path):
    add_user(db_path, TELEGRAM_ID)


def _make_state(telegram_id: int = TELEGRAM_ID) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=telegram_id, user_id=telegram_id)
    return FSMContext(storage=storage, key=key)


def _make_callback(data: str, telegram_id: int = TELEGRAM_ID):
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    callback.data = data
    callback.message = AsyncMock()
    return callback


def _make_message(text: str | None = None, telegram_id: int = TELEGRAM_ID):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    message.text = text
    return message


@pytest.mark.asyncio
async def test_start_shows_one_button_per_digest_item(db_path):
    state = _make_state()
    await state.update_data(digest_items=DIGEST_ITEMS)
    callback = _make_callback(CALLBACK_START)

    await on_authorpost_start(callback, state, db_path)

    args, kwargs = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_choose_item", "ru")
    buttons = [b for row in kwargs["reply_markup"].inline_keyboard for b in row]
    assert len(buttons) == len(DIGEST_ITEMS)


@pytest.mark.asyncio
async def test_start_reports_expired_digest_when_fsm_has_no_items(db_path):
    state = _make_state()
    callback = _make_callback(CALLBACK_START)

    await on_authorpost_start(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_digest_expired", "ru")


@pytest.mark.asyncio
async def test_start_reports_expired_digest_when_items_are_empty(db_path):
    state = _make_state()
    await state.update_data(digest_items=[])
    callback = _make_callback(CALLBACK_START)

    await on_authorpost_start(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_digest_expired", "ru")


@pytest.mark.asyncio
async def test_start_refuses_user_outside_whitelist(db_path):
    state = _make_state()
    await state.update_data(digest_items=DIGEST_ITEMS)
    callback = _make_callback(CALLBACK_START, telegram_id=999)

    await on_authorpost_start(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("error_not_whitelisted", "ru")


@pytest.mark.asyncio
async def test_item_choice_stores_source_text_and_offers_next_step(db_path):
    state = _make_state()
    await state.update_data(digest_items=DIGEST_ITEMS)
    callback = _make_callback(f"{CALLBACK_ITEM_PREFIX}:2")

    await on_authorpost_item(callback, state, db_path)

    data = await state.get_data()
    assert data["source_text"] == "Научная статья"
    args, kwargs = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_item_chosen", "ru", item="Научная статья")
    assert "reply_markup" in kwargs


@pytest.mark.asyncio
async def test_item_choice_out_of_range_reports_expired_digest(db_path):
    state = _make_state()
    await state.update_data(digest_items=DIGEST_ITEMS)
    callback = _make_callback(f"{CALLBACK_ITEM_PREFIX}:99")

    await on_authorpost_item(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_digest_expired", "ru")
    data = await state.get_data()
    assert "source_text" not in data


@pytest.mark.asyncio
async def test_item_choice_without_digest_items_reports_expired(db_path):
    state = _make_state()
    callback = _make_callback(f"{CALLBACK_ITEM_PREFIX}:0")

    await on_authorpost_item(callback, state, db_path)

    args, _ = callback.message.answer.call_args
    assert args[0] == get_string("authorpost_digest_expired", "ru")
