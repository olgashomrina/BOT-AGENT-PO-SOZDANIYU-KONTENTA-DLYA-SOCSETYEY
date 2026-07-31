from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import circle
from bot.storage.avatar_donors import add_donor, count_donors
from bot.storage.style_examples import (
    KIND_SPOKEN,
    KIND_WRITTEN,
    add_style_example,
    get_style_examples,
)
from bot.storage.voice_profiles import get_voice_profile, save_voice_profile

TELEGRAM_ID = 111
CONSENT_AT = "2026-07-28T10:00:00+00:00"


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


def _seed_double(db_path: str) -> None:
    add_donor(db_path, TELEGRAM_ID, "file-1", 40, "Расшифровка")
    add_style_example(db_path, TELEGRAM_ID, "Расшифровка", kind=KIND_SPOKEN)
    add_style_example(db_path, TELEGRAM_ID, "Письменный пост", kind=KIND_WRITTEN)
    save_voice_profile(db_path, TELEGRAM_ID, "elevenlabs", "voice-abc", CONSENT_AT)


@pytest.mark.asyncio
async def test_delete_request_asks_for_confirmation(db_path):
    _seed_double(db_path)
    callback = _callback()

    await circle.on_delete_request(callback, db_path=db_path)

    callback.message.answer.assert_awaited()
    assert count_donors(db_path, TELEGRAM_ID) == 1


@pytest.mark.asyncio
async def test_confirm_deletes_donors_voice_and_transcripts(db_path, state, monkeypatch):
    delete = AsyncMock()
    monkeypatch.setattr(circle, "delete_voice", delete)
    _seed_double(db_path)

    await circle.on_delete_confirm(_callback(), db_path=db_path, state=state)

    assert count_donors(db_path, TELEGRAM_ID) == 0
    assert get_voice_profile(db_path, TELEGRAM_ID) is None
    assert get_style_examples(db_path, TELEGRAM_ID, kind=KIND_SPOKEN) == []
    delete.assert_awaited_once_with("voice-abc")


@pytest.mark.asyncio
async def test_written_style_examples_survive_deletion(db_path, state, monkeypatch):
    # Удаление двойника не должно задевать сценарий авторского поста.
    monkeypatch.setattr(circle, "delete_voice", AsyncMock())
    _seed_double(db_path)

    await circle.on_delete_confirm(_callback(), db_path=db_path, state=state)

    assert get_style_examples(db_path, TELEGRAM_ID, kind=KIND_WRITTEN) == [
        "Письменный пост"
    ]


@pytest.mark.asyncio
async def test_local_data_is_wiped_even_if_provider_delete_fails(
    db_path, state, monkeypatch
):
    monkeypatch.setattr(
        circle,
        "delete_voice",
        AsyncMock(side_effect=circle.VoiceGatewayError("boom")),
    )
    _seed_double(db_path)

    await circle.on_delete_confirm(_callback(), db_path=db_path, state=state)

    assert count_donors(db_path, TELEGRAM_ID) == 0
    assert get_voice_profile(db_path, TELEGRAM_ID) is None


@pytest.mark.asyncio
async def test_delete_is_safe_without_a_double(db_path, state, monkeypatch):
    delete = AsyncMock()
    monkeypatch.setattr(circle, "delete_voice", delete)

    await circle.on_delete_confirm(_callback(), db_path=db_path, state=state)

    delete.assert_not_awaited()
