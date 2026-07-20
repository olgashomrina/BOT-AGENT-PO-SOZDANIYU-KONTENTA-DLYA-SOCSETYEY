from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, MessageOriginChannel

from bot.handlers.content import _resolve_language
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.storage.users import set_channel_id

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="channel")


class ChannelSetupStates(StatesGroup):
    waiting_for_forward = State()


@router.message(Command("channel"))
async def cmd_channel(message: Message, db_path: str, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    await state.set_state(ChannelSetupStates.waiting_for_forward)
    await message.answer(get_string("channel_setup_instructions", language))


async def _verify_bot_is_admin_with_post_rights(bot: Bot, channel_id: int) -> bool:
    try:
        bot_id = (await bot.get_me()).id
        member = await bot.get_chat_member(channel_id, bot_id)
    except TelegramAPIError:
        # Bot has no relationship at all to that chat (never added, kicked,
        # wrong id, etc.) — same friendly "not admin" outcome as an explicit
        # non-admin status, not a crash.
        return False

    if member.status == "creator":
        return True
    return member.status == "administrator" and bool(getattr(member, "can_post_messages", False))


@router.message(ChannelSetupStates.waiting_for_forward)
async def on_channel_forward(message: Message, db_path: str, bot: Bot, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    # WHY forward_origin instead of the deprecated forward_from_chat: Bot API
    # 7.0 replaced the old forward_from/forward_from_chat fields with
    # forward_origin, and Telegram no longer reliably populates the
    # deprecated fields for forwarded messages. forward_origin is a
    # MessageOriginChannel when (and only when) the message was forwarded
    # from a channel post.
    origin = message.forward_origin
    if not isinstance(origin, MessageOriginChannel):
        await message.answer(get_string("channel_setup_invalid_forward", language))
        return

    channel_id = origin.chat.id

    if not await _verify_bot_is_admin_with_post_rights(bot, channel_id):
        await message.answer(get_string("channel_setup_bot_not_admin", language))
        return

    set_channel_id(db_path, telegram_id, channel_id)
    await state.set_state(None)
    await message.answer(get_string("channel_setup_confirmation", language))
    logger.info(
        "Channel configured",
        extra={"user_id": telegram_id, "operation": "handler:channel"},
    )
