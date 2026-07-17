from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram import Dispatcher, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Chat, ErrorEvent, Message, Update, User

from bot.handlers.content import route_content
from bot.handlers.errors import handle_unexpected_error
from bot.handlers.errors import router as errors_router
from bot.locales.loader import get_string
from bot.services import input_processor
from bot.services.ai_gateway import (
    AIGatewayRateLimitError,
    AIGatewayUnavailableError,
    TranscriptionError,
)

TELEGRAM_ID = 111


def _make_message(text: str | None = None, voice=None):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=TELEGRAM_ID, language_code="ru")
    message.text = text
    message.voice = voice
    message.audio = None
    message.entities = None
    message.caption = None
    message.caption_entities = None
    return message


def _make_bot():
    bot = AsyncMock()
    bot.download = AsyncMock(return_value=io.BytesIO(b"fake-bytes"))
    return bot


def _make_state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=TELEGRAM_ID, user_id=TELEGRAM_ID)
    return FSMContext(storage=storage, key=key)


@pytest.mark.asyncio
async def test_link_extraction_failure_gives_friendly_message_and_no_crash(db_path, monkeypatch):
    message = _make_message(text="https://example.com/protected")
    bot = _make_bot()
    state = _make_state()

    technical_detail = "trafilatura: page requires JS rendering, blocked by paywall"

    def _raise(url):
        raise input_processor.LinkExtractionError(technical_detail)

    monkeypatch.setattr(input_processor, "extract_from_link", _raise)

    await route_content(message, db_path, bot, state)

    reply_text = message.answer.call_args[0][0]
    assert reply_text == get_string("error_link_extraction", "ru")
    assert technical_detail not in reply_text


@pytest.mark.asyncio
async def test_transcription_failure_gives_friendly_message_and_no_crash(db_path, monkeypatch):
    message = _make_message(voice=SimpleNamespace(file_id="abc"))
    bot = _make_bot()
    state = _make_state()

    technical_detail = "empty transcript payload from whisper endpoint"
    monkeypatch.setattr(
        input_processor,
        "handle_voice",
        AsyncMock(side_effect=TranscriptionError(technical_detail)),
    )

    await route_content(message, db_path, bot, state)

    reply_text = message.answer.call_args[0][0]
    assert reply_text == get_string("error_transcription", "ru")
    assert technical_detail not in reply_text


@pytest.mark.asyncio
async def test_ai_gateway_rate_limit_during_transcription_gives_friendly_message(
    db_path, monkeypatch
):
    message = _make_message(voice=SimpleNamespace(file_id="abc"))
    bot = _make_bot()
    state = _make_state()

    technical_detail = "HTTP 429 from ai-proxy.example"
    monkeypatch.setattr(
        input_processor,
        "handle_voice",
        AsyncMock(side_effect=AIGatewayRateLimitError(technical_detail)),
    )

    await route_content(message, db_path, bot, state)

    reply_text = message.answer.call_args[0][0]
    assert reply_text == get_string("error_rate_limit", "ru")
    assert technical_detail not in reply_text


@pytest.mark.asyncio
async def test_ai_gateway_unavailable_during_transcription_gives_friendly_message(
    db_path, monkeypatch
):
    message = _make_message(voice=SimpleNamespace(file_id="abc"))
    bot = _make_bot()
    state = _make_state()

    technical_detail = "Connection refused to ai-proxy.example:443"
    monkeypatch.setattr(
        input_processor,
        "handle_voice",
        AsyncMock(side_effect=AIGatewayUnavailableError(technical_detail)),
    )

    await route_content(message, db_path, bot, state)

    reply_text = message.answer.call_args[0][0]
    assert reply_text == get_string("error_ai_unavailable", "ru")
    assert technical_detail not in reply_text


# --- Phase 8: global error handler safety net (bot/handlers/errors.py) ---


def _make_real_update(text: str = "hi") -> Update:
    user = User(id=TELEGRAM_ID, is_bot=False, first_name="Test")
    chat = Chat(id=TELEGRAM_ID, type="private")
    message = Message(
        message_id=1, date=datetime.now(timezone.utc), chat=chat, from_user=user, text=text
    )
    return Update(update_id=1, message=message)


@pytest.mark.asyncio
async def test_global_error_handler_replies_with_friendly_message_and_no_crash(db_path, caplog):
    update = _make_real_update()
    technical_detail = "boom: unexpected bug, e.g. a KeyError deep in some handler"
    exc = ValueError(technical_detail)
    event = ErrorEvent(update=update, exception=exc)
    bot = AsyncMock()

    logger = logging.getLogger("bot")
    previous_propagate = logger.propagate
    logger.propagate = False
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger="bot"):
            await handle_unexpected_error(event, db_path, bot)
    finally:
        logger.removeHandler(caplog.handler)
        logger.propagate = previous_propagate

    bot.send_message.assert_awaited_once_with(TELEGRAM_ID, get_string("error_unexpected", "ru"))
    sent_text = bot.send_message.call_args[0][1]
    assert technical_detail not in sent_text

    error_records = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(error_records) == 1
    record = error_records[0]
    assert record.user_id == TELEGRAM_ID
    assert record.operation == "handler:message"
    assert record.error_class == "ValueError"
    assert record.exc_info is not None


@pytest.mark.asyncio
async def test_unhandled_exception_in_a_handler_does_not_crash_the_dispatcher(db_path):
    # Simulates a bug that Phases 4-7's local try/except blocks did not
    # anticipate. dispatcher.feed_update must complete normally (no
    # exception escaping) and the user still gets a friendly reply — proof
    # that registering errors_router in bot/main.py's build_dispatcher()
    # actually works end to end, not just as an isolated unit.
    dispatcher = Dispatcher()
    buggy_router = Router(name="buggy")

    @buggy_router.message()
    async def _buggy_handler(message):
        raise RuntimeError("kaboom, a bug nobody caught locally")

    dispatcher.include_router(buggy_router)
    dispatcher.include_router(errors_router)

    bot = AsyncMock()
    update = _make_real_update()

    result = await dispatcher.feed_update(bot, update, db_path=db_path)

    assert result is None
    bot.send_message.assert_awaited_once_with(TELEGRAM_ID, get_string("error_unexpected", "ru"))


# --- Phase 8: process-level crash handling in bot/main.py ---


@pytest.mark.asyncio
async def test_run_wrapper_notifies_owner_logs_critical_and_reraises_on_crash(monkeypatch, caplog):
    import bot.main as main_module

    fake_settings = SimpleNamespace(
        bot_token="fake-token",
        daily_limit=20,
        monthly_limit=300,
        db_path=":memory:",
        log_level="INFO",
        owner_chat_id=999,
    )
    monkeypatch.setattr(main_module, "load_settings", lambda: fake_settings)
    # Real setup_logging() sets propagate=False on the "bot" logger, which
    # would break caplog for every test running after this one in the same
    # session; it also writes real files under ./logs. Not under test here.
    monkeypatch.setattr(main_module, "setup_logging", lambda level: logging.getLogger("bot"))
    monkeypatch.setattr(main_module, "init_db", lambda path: None)

    fake_bot = AsyncMock()
    monkeypatch.setattr(main_module, "Bot", lambda token: fake_bot)

    fake_dispatcher = AsyncMock()
    fake_dispatcher.start_polling = AsyncMock(side_effect=RuntimeError("polling crashed"))
    monkeypatch.setattr(main_module, "build_dispatcher", lambda *args, **kwargs: fake_dispatcher)

    notify_mock = AsyncMock()
    monkeypatch.setattr(main_module, "notify_owner", notify_mock)

    logger = logging.getLogger("bot")
    previous_propagate = logger.propagate
    logger.propagate = False
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.CRITICAL, logger="bot"):
            with pytest.raises(RuntimeError, match="polling crashed"):
                await main_module.run()
    finally:
        logger.removeHandler(caplog.handler)
        logger.propagate = previous_propagate

    notify_mock.assert_awaited_once_with(fake_bot, 999, main_module._OWNER_CRASH_NOTICE)

    critical_records = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert len(critical_records) == 1
    assert critical_records[0].exc_info is not None

    fake_bot.session.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_run_wrapper_still_reraises_when_notify_owner_itself_fails(monkeypatch, caplog):
    import bot.main as main_module

    fake_settings = SimpleNamespace(
        bot_token="fake-token",
        daily_limit=20,
        monthly_limit=300,
        db_path=":memory:",
        log_level="INFO",
        owner_chat_id=999,
    )
    monkeypatch.setattr(main_module, "load_settings", lambda: fake_settings)
    monkeypatch.setattr(main_module, "setup_logging", lambda level: logging.getLogger("bot"))
    monkeypatch.setattr(main_module, "init_db", lambda path: None)

    fake_bot = AsyncMock()
    monkeypatch.setattr(main_module, "Bot", lambda token: fake_bot)

    fake_dispatcher = AsyncMock()
    fake_dispatcher.start_polling = AsyncMock(side_effect=RuntimeError("polling crashed"))
    monkeypatch.setattr(main_module, "build_dispatcher", lambda *args, **kwargs: fake_dispatcher)

    monkeypatch.setattr(
        main_module, "notify_owner", AsyncMock(side_effect=RuntimeError("owner notify also failed"))
    )

    logger = logging.getLogger("bot")
    previous_propagate = logger.propagate
    logger.propagate = False
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.CRITICAL, logger="bot"):
            with pytest.raises(RuntimeError, match="polling crashed"):
                await main_module.run()
    finally:
        logger.removeHandler(caplog.handler)
        logger.propagate = previous_propagate

    critical_records = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert len(critical_records) == 2
    fake_bot.session.close.assert_awaited_once()


def test_main_exits_with_nonzero_code_when_run_raises(monkeypatch):
    import bot.main as main_module

    async def _boom() -> None:
        raise RuntimeError("bot process crashed")

    monkeypatch.setattr(main_module, "run", _boom)

    with pytest.raises(SystemExit) as exc_info:
        main_module.main()

    assert exc_info.value.code == 1
