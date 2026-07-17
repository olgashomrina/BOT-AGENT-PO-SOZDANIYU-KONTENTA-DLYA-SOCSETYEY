from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers.content import (
    VoiceConfirmStates,
    detect_input_type,
    on_transcript_confirm,
    on_transcript_edit_request,
    on_transcript_edited_text,
    route_content,
)
from bot.locales.loader import get_string
from bot.services import input_processor
from bot.services.ai_gateway import AIGatewayTimeoutError, TranscriptionError

TELEGRAM_ID = 111


def _make_message(
    telegram_id: int = TELEGRAM_ID,
    text: str | None = None,
    voice=None,
    audio=None,
    entities=None,
    caption=None,
    caption_entities=None,
):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    message.text = text
    message.voice = voice
    message.audio = audio
    message.entities = entities
    message.caption = caption
    message.caption_entities = caption_entities
    return message


def _make_bot(audio_bytes: bytes = b"fake-bytes"):
    import io

    bot = AsyncMock()
    bot.download = AsyncMock(return_value=io.BytesIO(audio_bytes))
    return bot


def _make_state(telegram_id: int = TELEGRAM_ID) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=telegram_id, user_id=telegram_id)
    return FSMContext(storage=storage, key=key)


def _make_callback(telegram_id: int = TELEGRAM_ID, data: str = ""):
    callback = AsyncMock()
    callback.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    callback.data = data
    callback.message = AsyncMock()
    return callback


def test_detects_link_from_plain_url_in_text():
    message = _make_message(text="Посмотри вот это: https://example.com/article")

    assert detect_input_type(message) == "link"


def test_detects_link_from_url_entity():
    entity = SimpleNamespace(type="url")
    message = _make_message(text="example.com/article", entities=[entity])

    assert detect_input_type(message) == "link"


def test_detects_voice():
    message = _make_message(voice=SimpleNamespace(file_id="abc"))

    assert detect_input_type(message) == "voice"


def test_detects_audio():
    message = _make_message(audio=SimpleNamespace(file_id="abc"))

    assert detect_input_type(message) == "voice"


def test_detects_plain_text():
    message = _make_message(text="Просто текст без ссылок и голоса")

    assert detect_input_type(message) == "text"


@pytest.mark.asyncio
async def test_route_content_text_goes_straight_to_ready_stub(db_path):
    message = _make_message(text="Просто текст")
    bot = _make_bot()
    state = _make_state()

    await route_content(message, db_path, bot, state)

    message.answer.assert_awaited_once_with(get_string("content_ready_stub", "ru"))
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_route_content_link_success_goes_straight_to_ready_stub(db_path, monkeypatch):
    message = _make_message(text="https://example.com/article")
    bot = _make_bot()
    state = _make_state()

    monkeypatch.setattr(
        input_processor, "extract_from_link", lambda url: "Извлечённый текст статьи."
    )

    await route_content(message, db_path, bot, state)

    message.answer.assert_awaited_once_with(get_string("content_ready_stub", "ru"))


@pytest.mark.asyncio
async def test_route_content_link_failure_replies_with_friendly_error(db_path, monkeypatch):
    message = _make_message(text="https://example.com/blocked")
    bot = _make_bot()
    state = _make_state()

    def _raise(url):
        raise input_processor.LinkExtractionError("trafilatura returned None")

    monkeypatch.setattr(input_processor, "extract_from_link", _raise)

    await route_content(message, db_path, bot, state)

    message.answer.assert_awaited_once_with(get_string("error_link_extraction", "ru"))


@pytest.mark.asyncio
async def test_route_content_voice_shows_transcript_for_confirmation(db_path, monkeypatch):
    message = _make_message(voice=SimpleNamespace(file_id="abc"))
    bot = _make_bot()
    state = _make_state()

    monkeypatch.setattr(
        input_processor, "handle_voice", AsyncMock(return_value="Расшифрованный текст.")
    )

    await route_content(message, db_path, bot, state)

    message.answer.assert_awaited_once()
    args, kwargs = message.answer.call_args
    assert args[0] == get_string("transcript_preview", "ru", text="Расшифрованный текст.")
    assert "reply_markup" in kwargs

    assert await state.get_state() == VoiceConfirmStates.waiting_for_confirmation.state
    data = await state.get_data()
    assert data["transcript"] == "Расшифрованный текст."


@pytest.mark.asyncio
async def test_voice_confirm_flow_reaches_ready_stub(db_path, monkeypatch):
    message = _make_message(voice=SimpleNamespace(file_id="abc"))
    bot = _make_bot()
    state = _make_state()

    monkeypatch.setattr(
        input_processor, "handle_voice", AsyncMock(return_value="Расшифрованный текст.")
    )
    await route_content(message, db_path, bot, state)

    callback = _make_callback()
    await on_transcript_confirm(callback, state)

    callback.message.answer.assert_awaited_once_with(get_string("content_ready_stub", "ru"))
    callback.answer.assert_awaited_once()
    assert await state.get_state() is None
    assert (await state.get_data())["final_text"] == "Расшифрованный текст."


@pytest.mark.asyncio
async def test_voice_edit_flow_reaches_ready_stub_with_edited_text(db_path, monkeypatch):
    message = _make_message(voice=SimpleNamespace(file_id="abc"))
    bot = _make_bot()
    state = _make_state()

    monkeypatch.setattr(
        input_processor, "handle_voice", AsyncMock(return_value="Неверно распознанный текст.")
    )
    await route_content(message, db_path, bot, state)

    edit_callback = _make_callback()
    await on_transcript_edit_request(edit_callback, state)

    edit_callback.message.answer.assert_awaited_once_with(
        get_string("transcript_edit_prompt", "ru")
    )
    assert await state.get_state() == VoiceConfirmStates.waiting_for_edit.state

    edited_message = _make_message(text="Правильный текст, который я имел в виду.")
    await on_transcript_edited_text(edited_message, state)

    edited_message.answer.assert_awaited_once_with(get_string("content_ready_stub", "ru"))
    assert await state.get_state() is None
    assert (await state.get_data())["final_text"] == "Правильный текст, который я имел в виду."


@pytest.mark.asyncio
async def test_route_content_voice_transcription_error_replies_friendly_message(
    db_path, monkeypatch
):
    message = _make_message(voice=SimpleNamespace(file_id="abc"))
    bot = _make_bot()
    state = _make_state()

    monkeypatch.setattr(
        input_processor,
        "handle_voice",
        AsyncMock(side_effect=TranscriptionError("empty transcript from provider")),
    )

    await route_content(message, db_path, bot, state)

    message.answer.assert_awaited_once_with(get_string("error_transcription", "ru"))
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_route_content_voice_ai_gateway_error_replies_friendly_message(db_path, monkeypatch):
    message = _make_message(voice=SimpleNamespace(file_id="abc"))
    bot = _make_bot()
    state = _make_state()

    monkeypatch.setattr(
        input_processor,
        "handle_voice",
        AsyncMock(side_effect=AIGatewayTimeoutError("timed out after retries")),
    )

    await route_content(message, db_path, bot, state)

    message.answer.assert_awaited_once_with(get_string("error_ai_timeout", "ru"))
    assert await state.get_state() is None
