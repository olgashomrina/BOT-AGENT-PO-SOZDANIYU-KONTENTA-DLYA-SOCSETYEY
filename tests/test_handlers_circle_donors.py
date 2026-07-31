from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import circle
from bot.storage.avatar_donors import count_donors, get_donors
from bot.storage.style_examples import KIND_SPOKEN, get_style_examples

TELEGRAM_ID = 111


@pytest.fixture
def state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=TELEGRAM_ID, user_id=TELEGRAM_ID)
    return FSMContext(storage=storage, key=key)


def _callback() -> MagicMock:
    callback = MagicMock()
    callback.from_user.id = TELEGRAM_ID
    callback.from_user.language_code = "ru"
    callback.message.answer = AsyncMock()
    callback.answer = AsyncMock()
    return callback


def _video_note_message(duration: int = 40) -> MagicMock:
    message = MagicMock()
    message.from_user.id = TELEGRAM_ID
    message.from_user.language_code = "ru"
    message.video_note.file_id = "donor-file-1"
    message.video_note.duration = duration
    message.answer = AsyncMock()
    message.bot.download = AsyncMock()
    return message


@pytest.fixture(autouse=True)
def _stub_media(monkeypatch, tmp_path):
    async def fake_probe(path: str) -> float:
        return 40.0

    async def fake_extract(video_path: str, out_path: str) -> str:
        return out_path

    async def fake_transcribe(audio_bytes: bytes, language_hint=None) -> str:
        return "Расшифровка кружка"

    monkeypatch.setattr(circle, "probe_duration", fake_probe)
    monkeypatch.setattr(circle, "extract_audio", fake_extract)
    monkeypatch.setattr(circle, "transcribe", fake_transcribe)
    monkeypatch.setattr(circle, "_read_bytes", lambda path: b"audio")


@pytest.mark.asyncio
async def test_my_double_without_donors_shows_consent(db_path, state):
    callback = _callback()

    await circle.on_my_double(callback, db_path=db_path, state=state)

    callback.message.answer.assert_awaited()
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_consent_starts_donor_collection(db_path, state):
    callback = _callback()

    await circle.on_consent_accept(callback, db_path=db_path, state=state)

    assert await state.get_state() == circle.CircleStates.collecting_donors.state
    data = await state.get_data()
    assert data["consent_at"]


@pytest.mark.asyncio
async def test_video_note_is_saved_with_transcript(db_path, state):
    await circle.on_consent_accept(_callback(), db_path=db_path, state=state)
    message = _video_note_message()

    await circle.on_donor_video_note(message, db_path=db_path, state=state)

    donors = get_donors(db_path, TELEGRAM_ID)
    assert len(donors) == 1
    assert donors[0].file_id == "donor-file-1"
    assert donors[0].transcript == "Расшифровка кружка"


@pytest.mark.asyncio
async def test_transcript_is_stored_as_spoken_style_example(db_path, state):
    await circle.on_consent_accept(_callback(), db_path=db_path, state=state)

    await circle.on_donor_video_note(_video_note_message(), db_path=db_path, state=state)

    assert get_style_examples(db_path, TELEGRAM_ID, kind=KIND_SPOKEN) == [
        "Расшифровка кружка"
    ]


@pytest.mark.asyncio
async def test_short_donor_is_rejected(db_path, state, monkeypatch):
    async def short_probe(path: str) -> float:
        return 12.0

    monkeypatch.setattr(circle, "probe_duration", short_probe)
    await circle.on_consent_accept(_callback(), db_path=db_path, state=state)

    await circle.on_donor_video_note(_video_note_message(12), db_path=db_path, state=state)

    assert count_donors(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_failed_transcription_still_saves_donor(db_path, state, monkeypatch):
    async def failing_transcribe(audio_bytes: bytes, language_hint=None) -> str:
        raise circle.TranscriptionError("boom")

    monkeypatch.setattr(circle, "transcribe", failing_transcribe)
    await circle.on_consent_accept(_callback(), db_path=db_path, state=state)

    await circle.on_donor_video_note(_video_note_message(), db_path=db_path, state=state)

    donors = get_donors(db_path, TELEGRAM_ID)
    assert len(donors) == 1
    assert donors[0].transcript is None


@pytest.mark.asyncio
async def test_non_video_note_is_rejected_without_counting(db_path, state):
    await circle.on_consent_accept(_callback(), db_path=db_path, state=state)
    message = MagicMock()
    message.from_user.id = TELEGRAM_ID
    message.from_user.language_code = "ru"
    message.answer = AsyncMock()

    await circle.on_non_video_note(message, db_path=db_path)

    message.answer.assert_awaited()
    assert count_donors(db_path, TELEGRAM_ID) == 0
