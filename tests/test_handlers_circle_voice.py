from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import circle
from bot.storage.avatar_donors import add_donor
from bot.storage.voice_profiles import get_voice_profile

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
    callback.message.bot.download = AsyncMock()
    callback.answer = AsyncMock()
    return callback


@pytest.fixture(autouse=True)
def _stub_media(monkeypatch):
    async def fake_extract(video_path: str, out_path: str) -> str:
        return out_path

    async def fake_concat(paths: list[str], out_path: str) -> str:
        return out_path

    monkeypatch.setattr(circle, "extract_audio", fake_extract)
    monkeypatch.setattr(circle, "concat_audio", fake_concat)
    monkeypatch.setattr(circle, "_read_bytes", lambda path: b"audio")


def _seed_donors(db_path: str, count: int = 3) -> None:
    for index in range(count):
        add_donor(db_path, TELEGRAM_ID, f"file-{index}", 40, "Расшифровка")


@pytest.mark.asyncio
async def test_voice_profile_is_created(db_path, state, monkeypatch):
    clone = AsyncMock(return_value="voice-abc")
    monkeypatch.setattr(circle, "clone_voice", clone)
    _seed_donors(db_path)
    await state.update_data(consent_at=CONSENT_AT)

    await circle.on_donors_done(_callback(), db_path=db_path, state=state)

    profile = get_voice_profile(db_path, TELEGRAM_ID)
    assert profile is not None
    assert profile.external_voice_id == "voice-abc"
    assert profile.consent_at == CONSENT_AT
    clone.assert_awaited_once()


@pytest.mark.asyncio
async def test_state_is_reset_after_success(db_path, state, monkeypatch):
    monkeypatch.setattr(circle, "clone_voice", AsyncMock(return_value="voice-abc"))
    _seed_donors(db_path)
    await state.set_state(circle.CircleStates.collecting_donors)
    await state.update_data(consent_at=CONSENT_AT)

    await circle.on_donors_done(_callback(), db_path=db_path, state=state)

    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_refuses_when_not_enough_donors(db_path, state, monkeypatch):
    clone = AsyncMock(return_value="voice-abc")
    monkeypatch.setattr(circle, "clone_voice", clone)
    _seed_donors(db_path, count=1)
    await state.update_data(consent_at=CONSENT_AT)

    await circle.on_donors_done(_callback(), db_path=db_path, state=state)

    assert get_voice_profile(db_path, TELEGRAM_ID) is None
    clone.assert_not_awaited()


@pytest.mark.asyncio
async def test_provider_failure_leaves_no_profile(db_path, state, monkeypatch):
    monkeypatch.setattr(
        circle,
        "clone_voice",
        AsyncMock(side_effect=circle.VoiceGatewayError("boom")),
    )
    _seed_donors(db_path)
    await state.update_data(consent_at=CONSENT_AT)
    callback = _callback()

    await circle.on_donors_done(callback, db_path=db_path, state=state)

    assert get_voice_profile(db_path, TELEGRAM_ID) is None
    callback.message.answer.assert_awaited()


@pytest.mark.asyncio
async def test_missing_consent_timestamp_falls_back_to_now(db_path, state, monkeypatch):
    # FSM в памяти: перезапуск бота между согласием и нажатием «Готово»
    # стирает данные. Профиль всё равно должен получить отметку согласия.
    monkeypatch.setattr(circle, "clone_voice", AsyncMock(return_value="voice-abc"))
    _seed_donors(db_path)

    await circle.on_donors_done(_callback(), db_path=db_path, state=state)

    profile = get_voice_profile(db_path, TELEGRAM_ID)
    assert profile is not None
    assert profile.consent_at
