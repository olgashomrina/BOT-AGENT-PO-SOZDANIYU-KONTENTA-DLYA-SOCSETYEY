from __future__ import annotations

import pytest

from bot.services import local_transcriber
from bot.services.ai_gateway import TranscriptionError


class _Segment:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModel:
    def __init__(self, segments: list[_Segment]) -> None:
        self._segments = segments
        self.calls: list[dict] = []

    def transcribe(self, audio, **kwargs):
        self.calls.append(kwargs)
        return iter(self._segments), object()


@pytest.mark.asyncio
async def test_segments_are_joined_into_one_text(monkeypatch):
    """Whisper отдаёт речь кусками, а боту нужен один связный текст."""
    model = _FakeModel([_Segment(" Создай мне пост "), _Segment(" про отпуск. ")])
    monkeypatch.setattr(local_transcriber, "_load_model", lambda *a, **k: model)

    result = await local_transcriber.transcribe_locally(b"ogg-bytes", language_hint="ru")

    assert result == "Создай мне пост про отпуск."


@pytest.mark.asyncio
async def test_language_hint_is_passed_to_the_model(monkeypatch):
    """Без подсказки языка Whisper иногда принимает русскую речь за другой язык."""
    model = _FakeModel([_Segment("текст")])
    monkeypatch.setattr(local_transcriber, "_load_model", lambda *a, **k: model)

    await local_transcriber.transcribe_locally(b"ogg-bytes", language_hint="ru")

    assert model.calls[0]["language"] == "ru"


@pytest.mark.asyncio
async def test_empty_result_raises_transcription_error(monkeypatch):
    """Пустая расшифровка — это отказ, а не пустой пост.

    Без этого пользователь получил бы сгенерированный из пустоты текст, не
    имеющий отношения к тому, что он наговорил.
    """
    monkeypatch.setattr(local_transcriber, "_load_model", lambda *a, **k: _FakeModel([]))

    with pytest.raises(TranscriptionError):
        await local_transcriber.transcribe_locally(b"ogg-bytes", language_hint="ru")


@pytest.mark.asyncio
async def test_model_failure_is_reported_as_transcription_error(monkeypatch):
    """Сбой модели должен выглядеть для хендлеров так же, как сбой сервиса."""

    def _boom(*args, **kwargs):
        raise RuntimeError("model file is corrupt")

    monkeypatch.setattr(local_transcriber, "_load_model", _boom)

    with pytest.raises(TranscriptionError):
        await local_transcriber.transcribe_locally(b"ogg-bytes", language_hint="ru")
