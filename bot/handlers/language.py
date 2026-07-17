from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.keyboards.language import CALLBACK_PREFIX, build_language_keyboard
from bot.locales.loader import DEFAULT_LANGUAGE, get_string
from bot.storage.users import get_interface_language, set_interface_language

router = Router(name="language")


@router.message(Command("language"))
async def cmd_language(message: Message, db_path: str) -> None:
    language = get_interface_language(db_path, message.from_user.id) or DEFAULT_LANGUAGE
    await message.answer(
        get_string("language_prompt", language), reply_markup=build_language_keyboard()
    )


@router.callback_query(F.data.startswith(CALLBACK_PREFIX))
async def on_language_selected(callback: CallbackQuery, db_path: str) -> None:
    language = callback.data.removeprefix(CALLBACK_PREFIX)
    set_interface_language(db_path, callback.from_user.id, language)
    await callback.message.answer(get_string("language_set_confirmation", language))
    await callback.answer()
