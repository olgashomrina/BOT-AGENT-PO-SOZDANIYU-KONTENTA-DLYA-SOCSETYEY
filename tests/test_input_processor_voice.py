from __future__ import annotations

import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.services import input_processor
from bot.services.ai_gateway import AIGatewayTimeoutError, AIGatewayUnavailableError, TranscriptionError


def _make_bot(audio_bytes: bytes = b"fake-ogg-bytes"):
    bot = AsyncMock()
    bot.download = AsyncMock(return_value=io.BytesIO(audio_bytes))
    return bot


def _make_message(voice=None, audio=None):
    message = SimpleNamespace(voice=voice, audio=audio)
    return message


@pytest.mark.asyncio
async def test_handle_voice_returns_transcript_on_success(monkeypatch):
    bot = _make_bot(b"audio-data")
    message = _make_message(voice=SimpleNamespace(file_id="abc"))

    transcribe_mock = AsyncMock(return_value="Расшифрованный текст.")
    monkeypatch.setattr(input_processor.ai_gateway, "transcribe", transcribe_mock)

    result = await input_processor.handle_voice(bot, message, language_hint="ru")

    assert result == "Расшифрованный текст."
    bot.download.assert_awaited_once_with(message.voice)
    transcribe_mock.assert_awaited_once_with(b"audio-data", language_hint="ru")


@pytest.mark.asyncio
async def test_handle_voice_uses_audio_when_voice_missing(monkeypatch):
    bot = _make_bot(b"audio-data")
    message = _make_message(audio=SimpleNamespace(file_id="xyz"))

    monkeypatch.setattr(
        input_processor.ai_gateway, "transcribe", AsyncMock(return_value="ok")
    )

    await input_processor.handle_voice(bot, message)

    bot.download.assert_awaited_once_with(message.audio)


@pytest.mark.asyncio
async def test_handle_voice_propagates_transcription_error(monkeypatch):
    bot = _make_bot()
    message = _make_message(voice=SimpleNamespace(file_id="abc"))

    monkeypatch.setattr(
        input_processor.ai_gateway,
        "transcribe",
        AsyncMock(side_effect=TranscriptionError("empty transcript")),
    )

    with pytest.raises(TranscriptionError):
        await input_processor.handle_voice(bot, message)


@pytest.mark.asyncio
async def test_handle_voice_propagates_network_level_ai_gateway_errors(monkeypatch):
    bot = _make_bot()
    message = _make_message(voice=SimpleNamespace(file_id="abc"))

    monkeypatch.setattr(
        input_processor.ai_gateway,
        "transcribe",
        AsyncMock(side_effect=AIGatewayTimeoutError("timed out")),
    )

    with pytest.raises(AIGatewayTimeoutError):
        await input_processor.handle_voice(bot, message)


@pytest.mark.asyncio
async def test_handle_voice_propagates_unavailable_error(monkeypatch):
    bot = _make_bot()
    message = _make_message(voice=SimpleNamespace(file_id="abc"))

    monkeypatch.setattr(
        input_processor.ai_gateway,
        "transcribe",
        AsyncMock(side_effect=AIGatewayUnavailableError("no connection")),
    )

    with pytest.raises(AIGatewayUnavailableError):
        await input_processor.handle_voice(bot, message)
