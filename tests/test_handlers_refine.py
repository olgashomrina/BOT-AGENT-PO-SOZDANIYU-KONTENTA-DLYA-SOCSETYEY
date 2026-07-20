from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import SendMessage

from bot.handlers.refine import on_refine_more, on_refine_publish, on_refine_shorten
from bot.locales.loader import get_string
from bot.services import content_generator, output_formatter
from bot.services.ai_gateway import AIGatewayTimeoutError
from bot.storage.limits import get_daily_count
from bot.storage.users import set_channel_id
from bot.storage.whitelist import add_user

TELEGRAM_ID = 111


@pytest.fixture(autouse=True)
def _ai_gateway_env(monkeypatch):
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


async def _seed_finished_session(
    state: FSMContext,
    source_text: str = "Исходный текст статьи.",
    content_language: str = "ru",
    language: str = "ru",
) -> None:
    await state.update_data(source_text=source_text, content_language=content_language, language=language)
    await state.set_state(None)


def _make_callback(telegram_id: int = TELEGRAM_ID, data: str = "", language_code: str = "ru"):
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=telegram_id, language_code=language_code)
    callback.data = data
    callback.message = AsyncMock()
    return callback


@pytest.mark.asyncio
async def test_refine_more_generates_and_sends_new_variant(db_path, monkeypatch):
    state = _make_state()
    await _seed_finished_session(state)

    mock_generate = AsyncMock(return_value=["Новый вариант поста"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(data="refine:more:telegram:1")
    await on_refine_more(callback, state, db_path)

    mock_generate.assert_awaited_once_with(
        "Исходный текст статьи.", "telegram", "ru", count=1, extra_instruction=None
    )
    callback.message.answer.assert_awaited_once()
    args, kwargs = callback.message.answer.call_args
    assert args[0] == output_formatter.format_variant("Новый вариант поста")
    assert kwargs["parse_mode"] == output_formatter.PARSE_MODE
    assert "reply_markup" in kwargs
    callback.answer.assert_awaited_once()
    assert get_daily_count(db_path, TELEGRAM_ID) == 1


@pytest.mark.asyncio
async def test_refine_shorten_passes_shorten_instruction(db_path, monkeypatch):
    state = _make_state()
    await _seed_finished_session(state)

    mock_generate = AsyncMock(return_value=["Короткий вариант"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(data="refine:shorten:vk:1")
    await on_refine_shorten(callback, state, db_path)

    mock_generate.assert_awaited_once_with(
        "Исходный текст статьи.",
        "vk",
        "ru",
        count=1,
        extra_instruction=content_generator.SHORTEN_INSTRUCTION,
    )
    callback.message.answer.assert_awaited_once()
    args, _ = callback.message.answer.call_args
    assert args[0] == output_formatter.format_variant("Короткий вариант")
    assert get_daily_count(db_path, TELEGRAM_ID) == 1


@pytest.mark.asyncio
async def test_refine_blocked_when_daily_limit_exceeded_does_not_call_generate(db_path, monkeypatch):
    monkeypatch.setenv("DAILY_LIMIT", "0")
    state = _make_state()
    await _seed_finished_session(state, language="en")

    mock_generate = AsyncMock(return_value=["Не должно быть отправлено"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(data="refine:more:telegram:1", language_code="en")
    await on_refine_more(callback, state, db_path)

    mock_generate.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_daily_limit_exceeded", "en"))
    callback.answer.assert_awaited_once()
    assert get_daily_count(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_refine_blocked_when_at_limit_uses_stored_interface_language(db_path, monkeypatch):
    monkeypatch.setenv("DAILY_LIMIT", "0")
    state = _make_state()
    await _seed_finished_session(state, language="vi")

    mock_generate = AsyncMock(return_value=["x"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(data="refine:shorten:telegram:1", language_code="en")
    await on_refine_shorten(callback, state, db_path)

    mock_generate.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_daily_limit_exceeded", "vi"))


@pytest.mark.asyncio
async def test_refine_with_missing_fsm_data_does_not_crash(db_path, monkeypatch):
    state = _make_state()

    mock_generate = AsyncMock(return_value=["x"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(data="refine:more:telegram:1")
    await on_refine_more(callback, state, db_path)

    mock_generate.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(
        get_string("error_refine_missing_context", "ru")
    )
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_refine_ai_gateway_error_replies_friendly_message_and_does_not_increment(
    db_path, monkeypatch
):
    state = _make_state()
    await _seed_finished_session(state)

    mock_generate = AsyncMock(side_effect=AIGatewayTimeoutError("timed out"))
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(data="refine:more:telegram:1")
    await on_refine_more(callback, state, db_path)

    callback.message.answer.assert_awaited_once_with(get_string("error_ai_timeout", "ru"))
    callback.answer.assert_awaited_once()
    assert get_daily_count(db_path, TELEGRAM_ID) == 0


@pytest.mark.parametrize(
    "handler, data",
    [
        (on_refine_more, "refine:more:telegram:1"),
        (on_refine_shorten, "refine:shorten:telegram:1"),
    ],
)
@pytest.mark.asyncio
async def test_refine_blocked_when_not_whitelisted_does_not_call_generate(
    db_path, monkeypatch, handler, data
):
    NOT_WHITELISTED_ID = 999
    state = _make_state(NOT_WHITELISTED_ID)
    await _seed_finished_session(state)

    mock_generate = AsyncMock(return_value=["Не должно быть отправлено"])
    monkeypatch.setattr(content_generator, "generate_variants", mock_generate)

    callback = _make_callback(telegram_id=NOT_WHITELISTED_ID, data=data)
    await handler(callback, state, db_path)

    mock_generate.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))
    callback.answer.assert_awaited_once()
    assert get_daily_count(db_path, NOT_WHITELISTED_ID) == 0


CHANNEL_ID = -1001234567890


@pytest.mark.asyncio
async def test_publish_success_sends_formatted_variant_to_channel(db_path):
    set_channel_id(db_path, TELEGRAM_ID, CHANNEL_ID)
    state = _make_state()
    await _seed_finished_session(state)

    callback = _make_callback(data="refine:publish:telegram:1")
    callback.message.text = "Готовый вариант поста"
    bot = AsyncMock()

    await on_refine_publish(callback, state, db_path, bot)

    bot.send_message.assert_awaited_once_with(
        CHANNEL_ID,
        output_formatter.format_variant("Готовый вариант поста"),
        parse_mode=output_formatter.PARSE_MODE,
    )
    callback.message.answer.assert_awaited_once_with(get_string("publish_success", "ru"))
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_without_configured_channel_prompts_setup_and_does_not_send(db_path):
    state = _make_state()
    await _seed_finished_session(state)

    callback = _make_callback(data="refine:publish:telegram:1")
    callback.message.text = "Готовый вариант поста"
    bot = AsyncMock()

    await on_refine_publish(callback, state, db_path, bot)

    bot.send_message.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(
        get_string("publish_no_channel_configured", "ru")
    )
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_telegram_failure_replies_friendly_error(db_path):
    set_channel_id(db_path, TELEGRAM_ID, CHANNEL_ID)
    state = _make_state()
    await _seed_finished_session(state)

    callback = _make_callback(data="refine:publish:telegram:1")
    callback.message.text = "Готовый вариант поста"
    bot = AsyncMock()
    bot.send_message = AsyncMock(
        side_effect=TelegramBadRequest(
            method=SendMessage(chat_id=CHANNEL_ID, text="x"), message="bot was kicked"
        )
    )

    await on_refine_publish(callback, state, db_path, bot)

    callback.message.answer.assert_awaited_once_with(get_string("publish_failed", "ru"))
    callback.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_blocked_when_not_whitelisted_does_not_send(db_path):
    NOT_WHITELISTED_ID = 999
    state = _make_state(NOT_WHITELISTED_ID)
    await _seed_finished_session(state)

    callback = _make_callback(telegram_id=NOT_WHITELISTED_ID, data="refine:publish:telegram:1")
    callback.message.text = "Готовый вариант поста"
    bot = AsyncMock()

    await on_refine_publish(callback, state, db_path, bot)

    bot.send_message.assert_not_awaited()
    callback.message.answer.assert_awaited_once_with(get_string("error_not_whitelisted", "ru"))
    callback.answer.assert_awaited_once()
