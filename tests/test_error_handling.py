from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.content import route_content
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
