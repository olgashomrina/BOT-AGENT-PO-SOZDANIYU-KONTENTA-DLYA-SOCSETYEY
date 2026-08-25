from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import double
from bot.storage.avatar_faces import get_face, save_face
from bot.storage.avatar_looks import (
    SOURCE_GENERATED,
    SOURCE_UPLOADED,
    add_look,
    get_active_look,
    get_looks,
)
from bot.storage.costs import get_monthly_total
from bot.storage.whitelist import add_user

TELEGRAM_ID = 1101


@pytest.fixture(autouse=True)
def _whitelisted(db_path):
    # Платные кнопки закрыты вайтлистом, а он же и есть список подписчиков.
    # Без этой строчки каждый тест ниже проверял бы отказ, а не сценарий.
    add_user(db_path, TELEGRAM_ID)


@pytest.fixture
def state() -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=TELEGRAM_ID, user_id=TELEGRAM_ID)
    return FSMContext(storage=storage, key=key)


def _callback(data: str = "") -> MagicMock:
    callback = MagicMock()
    callback.data = data
    callback.from_user.id = TELEGRAM_ID
    callback.from_user.language_code = "ru"
    callback.message.answer = AsyncMock()
    callback.message.answer_photo = AsyncMock()
    callback.message.bot.download = AsyncMock()
    callback.answer = AsyncMock()
    return callback


def _photo_message() -> MagicMock:
    message = MagicMock()
    message.from_user.id = TELEGRAM_ID
    message.from_user.language_code = "ru"
    message.caption = None
    message.photo = [MagicMock(file_id="photo-small"), MagicMock(file_id="photo-big")]
    message.answer = AsyncMock()
    message.answer_photo = AsyncMock(return_value=_sent_photo())
    message.bot.download = AsyncMock()
    return message


def _text_message(text: str) -> MagicMock:
    message = MagicMock()
    message.from_user.id = TELEGRAM_ID
    message.from_user.language_code = "ru"
    message.text = text
    message.photo = None
    message.answer = AsyncMock()
    # Возврат обязан нести настоящую строку: file_id уходит в SQLite, и
    # MagicMock там падает с InterfaceError, а не с понятной ошибкой теста.
    message.answer_photo = AsyncMock(return_value=_sent_photo())
    message.bot.download = AsyncMock()
    return message


def _sent_photo() -> MagicMock:
    return MagicMock(photo=[MagicMock(file_id="look-1")])


@pytest.mark.asyncio
async def test_face_photo_is_stored_at_the_highest_resolution(db_path, state):
    # Telegram присылает лесенку размеров; сходство лица держится на резкости,
    # поэтому берём последний, самый крупный.
    await state.set_state(double.DoubleStates.waiting_face)

    await double.on_face_photo(_photo_message(), db_path=db_path, state=state)

    assert get_face(db_path, TELEGRAM_ID).file_id == "photo-big"
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_non_photo_while_waiting_for_a_face_is_answered_not_swallowed(
    db_path, state
):
    await state.set_state(double.DoubleStates.waiting_face)
    message = _text_message("вот держи")

    await double.on_face_wrong_input(message, db_path=db_path, state=state)

    message.answer.assert_awaited_once()
    assert get_face(db_path, TELEGRAM_ID) is None


@pytest.mark.asyncio
async def test_uploaded_look_is_saved_without_spending_money(db_path, state):
    await state.set_state(double.DoubleStates.waiting_look_photo)

    await double.on_look_photo(_photo_message(), db_path=db_path, state=state)

    looks = get_looks(db_path, TELEGRAM_ID)
    assert len(looks) == 1
    assert looks[0].source == SOURCE_UPLOADED
    assert get_monthly_total(db_path) == 0


@pytest.mark.asyncio
async def test_describing_a_look_without_a_face_refuses_before_paying(
    db_path, state, monkeypatch
):
    edit = AsyncMock(return_value=b"image")
    monkeypatch.setattr(double, "edit_image", edit)
    callback = _callback()

    await double.on_look_add_prompt(callback, db_path=db_path, state=state)

    edit.assert_not_awaited()
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_described_look_is_generated_and_charged(db_path, state, monkeypatch):
    save_face(db_path, TELEGRAM_ID, "photo-face")
    monkeypatch.setattr(double, "edit_image", AsyncMock(return_value=b"image"))
    monkeypatch.setattr(double, "_read_bytes", lambda path: b"face-bytes")
    await state.set_state(double.DoubleStates.waiting_look_prompt)

    await double.on_look_prompt(
        _text_message("белая рубашка, тёмный фон"), db_path=db_path, state=state
    )

    looks = get_looks(db_path, TELEGRAM_ID)
    assert looks[0].source == SOURCE_GENERATED
    assert looks[0].prompt == "белая рубашка, тёмный фон"
    # 4 ₽ за образ должны быть видны в /costs.
    assert get_monthly_total(db_path) == pytest.approx(4.0)


@pytest.mark.asyncio
async def test_a_hair_change_is_warned_about_but_still_done(
    db_path, state, monkeypatch
):
    save_face(db_path, TELEGRAM_ID, "photo-face")
    monkeypatch.setattr(double, "edit_image", AsyncMock(return_value=b"image"))
    monkeypatch.setattr(double, "_read_bytes", lambda path: b"face-bytes")
    await state.set_state(double.DoubleStates.waiting_look_prompt)
    message = _text_message("сделай каре")

    await double.on_look_prompt(message, db_path=db_path, state=state)

    warned = [call.args[0] for call in message.answer.await_args_list]
    assert any("причёск" in text.lower() or "модель" in text.lower() for text in warned)
    assert len(get_looks(db_path, TELEGRAM_ID)) == 1


@pytest.mark.asyncio
async def test_failed_generation_does_not_save_a_look(db_path, state, monkeypatch):
    from bot.services.ai_gateway import AIGatewayUnavailableError

    save_face(db_path, TELEGRAM_ID, "photo-face")
    monkeypatch.setattr(
        double, "edit_image", AsyncMock(side_effect=AIGatewayUnavailableError("нет сети"))
    )
    monkeypatch.setattr(double, "_read_bytes", lambda path: b"face-bytes")
    await state.set_state(double.DoubleStates.waiting_look_prompt)

    await double.on_look_prompt(_text_message("студия"), db_path=db_path, state=state)

    assert get_looks(db_path, TELEGRAM_ID) == []


@pytest.mark.asyncio
async def test_picking_a_look_makes_it_active(db_path, state):
    add_look(db_path, TELEGRAM_ID, "img-1", "студия", SOURCE_UPLOADED)
    second = add_look(db_path, TELEGRAM_ID, "img-2", "улица", SOURCE_UPLOADED)

    await double.on_look_activate(
        _callback(f"double:look_on:{second}"), db_path=db_path, state=state
    )

    assert get_active_look(db_path, TELEGRAM_ID).id == second


@pytest.mark.asyncio
async def test_deleting_a_look_removes_it(db_path, state):
    look_id = add_look(db_path, TELEGRAM_ID, "img-1", "студия", SOURCE_UPLOADED)

    await double.on_look_delete(
        _callback(f"double:look_del:{look_id}"), db_path=db_path, state=state
    )

    assert get_looks(db_path, TELEGRAM_ID) == []
