from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import GetChatMember
from aiogram.types import Chat, MessageOriginChannel

from bot.handlers.channel import ChannelSetupStates, cmd_channel, on_channel_forward
from bot.locales.loader import get_string
from bot.storage.users import get_channel_id

TELEGRAM_ID = 111
CHANNEL_ID = -1001234567890


def _make_state(telegram_id: int = TELEGRAM_ID) -> FSMContext:
    storage = MemoryStorage()
    key = StorageKey(bot_id=1, chat_id=telegram_id, user_id=telegram_id)
    return FSMContext(storage=storage, key=key)


def _make_message(telegram_id: int = TELEGRAM_ID, forward_origin=None):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    message.forward_origin = forward_origin
    return message


def _channel_origin(channel_id: int = CHANNEL_ID) -> MessageOriginChannel:
    return MessageOriginChannel(
        date=0,
        chat=Chat(id=channel_id, type="channel"),
        message_id=1,
    )


def _make_bot(status: str = "administrator", can_post_messages: bool = True):
    bot = AsyncMock()
    bot.get_me = AsyncMock(return_value=SimpleNamespace(id=999))
    member = SimpleNamespace(status=status, can_post_messages=can_post_messages)
    bot.get_chat_member = AsyncMock(return_value=member)
    return bot


@pytest.mark.asyncio
async def test_cmd_channel_shows_instructions_and_sets_waiting_state(db_path):
    message = _make_message()
    state = _make_state()

    await cmd_channel(message, db_path, state)

    message.answer.assert_awaited_once_with(get_string("channel_setup_instructions", "ru"))
    assert await state.get_state() == ChannelSetupStates.waiting_for_forward.state


@pytest.mark.asyncio
async def test_forward_from_channel_with_admin_and_post_rights_saves_channel(db_path):
    message = _make_message(forward_origin=_channel_origin())
    bot = _make_bot(status="administrator", can_post_messages=True)
    state = _make_state()
    await state.set_state(ChannelSetupStates.waiting_for_forward)

    await on_channel_forward(message, db_path, bot, state)

    assert get_channel_id(db_path, TELEGRAM_ID) == CHANNEL_ID
    message.answer.assert_awaited_once_with(get_string("channel_setup_confirmation", "ru"))
    assert await state.get_state() is None


@pytest.mark.asyncio
async def test_forward_from_channel_where_creator_saves_channel(db_path):
    message = _make_message(forward_origin=_channel_origin())
    bot = _make_bot(status="creator", can_post_messages=None)
    state = _make_state()
    await state.set_state(ChannelSetupStates.waiting_for_forward)

    await on_channel_forward(message, db_path, bot, state)

    assert get_channel_id(db_path, TELEGRAM_ID) == CHANNEL_ID


@pytest.mark.asyncio
async def test_forward_from_channel_bot_not_admin_gives_friendly_error_and_keeps_state(db_path):
    message = _make_message(forward_origin=_channel_origin())
    bot = _make_bot(status="member", can_post_messages=None)
    state = _make_state()
    await state.set_state(ChannelSetupStates.waiting_for_forward)

    await on_channel_forward(message, db_path, bot, state)

    assert get_channel_id(db_path, TELEGRAM_ID) is None
    message.answer.assert_awaited_once_with(get_string("channel_setup_bot_not_admin", "ru"))
    assert await state.get_state() == ChannelSetupStates.waiting_for_forward.state


@pytest.mark.asyncio
async def test_forward_from_channel_admin_without_post_rights_gives_friendly_error(db_path):
    message = _make_message(forward_origin=_channel_origin())
    bot = _make_bot(status="administrator", can_post_messages=False)
    state = _make_state()
    await state.set_state(ChannelSetupStates.waiting_for_forward)

    await on_channel_forward(message, db_path, bot, state)

    assert get_channel_id(db_path, TELEGRAM_ID) is None
    message.answer.assert_awaited_once_with(get_string("channel_setup_bot_not_admin", "ru"))
    assert await state.get_state() == ChannelSetupStates.waiting_for_forward.state


@pytest.mark.asyncio
async def test_forward_verification_raising_telegram_error_gives_friendly_error(db_path):
    message = _make_message(forward_origin=_channel_origin())
    bot = AsyncMock()
    bot.get_me = AsyncMock(return_value=SimpleNamespace(id=999))
    bot.get_chat_member = AsyncMock(
        side_effect=TelegramBadRequest(
            method=GetChatMember(chat_id=CHANNEL_ID, user_id=999), message="chat not found"
        )
    )
    state = _make_state()
    await state.set_state(ChannelSetupStates.waiting_for_forward)

    await on_channel_forward(message, db_path, bot, state)

    assert get_channel_id(db_path, TELEGRAM_ID) is None
    message.answer.assert_awaited_once_with(get_string("channel_setup_bot_not_admin", "ru"))
    assert await state.get_state() == ChannelSetupStates.waiting_for_forward.state


@pytest.mark.asyncio
async def test_non_forwarded_message_gives_friendly_error_and_keeps_state(db_path):
    message = _make_message(forward_origin=None)
    bot = _make_bot()
    state = _make_state()
    await state.set_state(ChannelSetupStates.waiting_for_forward)

    await on_channel_forward(message, db_path, bot, state)

    assert get_channel_id(db_path, TELEGRAM_ID) is None
    message.answer.assert_awaited_once_with(get_string("channel_setup_invalid_forward", "ru"))
    assert await state.get_state() == ChannelSetupStates.waiting_for_forward.state
    bot.get_chat_member.assert_not_awaited()


@pytest.mark.asyncio
async def test_forwarded_from_non_channel_gives_friendly_error(db_path):
    forwarded_user_origin = SimpleNamespace(type="user")
    message = _make_message(forward_origin=forwarded_user_origin)
    bot = _make_bot()
    state = _make_state()
    await state.set_state(ChannelSetupStates.waiting_for_forward)

    await on_channel_forward(message, db_path, bot, state)

    assert get_channel_id(db_path, TELEGRAM_ID) is None
    message.answer.assert_awaited_once_with(get_string("channel_setup_invalid_forward", "ru"))
    assert await state.get_state() == ChannelSetupStates.waiting_for_forward.state
