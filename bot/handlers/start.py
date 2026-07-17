from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.locales.loader import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, get_string
from bot.storage.users import get_interface_language, set_interface_language

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, db_path: str) -> None:
    telegram_id = message.from_user.id
    language = get_interface_language(db_path, telegram_id)
    if language is None:
        language_code = message.from_user.language_code
        language = language_code if language_code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
        set_interface_language(db_path, telegram_id, language)
    await message.answer(get_string("start_greeting", language))


@router.message(Command("help"))
async def cmd_help(message: Message, db_path: str) -> None:
    telegram_id = message.from_user.id
    language = get_interface_language(db_path, telegram_id)
    if language is None:
        language_code = message.from_user.language_code
        language = language_code if language_code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    await message.answer(get_string("help_text", language))
