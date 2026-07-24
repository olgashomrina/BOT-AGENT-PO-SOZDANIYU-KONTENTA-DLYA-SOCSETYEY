from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from bot.config import load_settings
from bot.handlers.content import _resolve_language
from bot.handlers.refine import _check_whitelist_or_reply
from bot.keyboards.start import (
    CALLBACK_CAPABILITIES,
    CALLBACK_CREATE_POST,
    CALLBACK_TEXT_HINT,
    build_create_post_keyboard,
    build_persistent_start_keyboard,
    build_start_menu_keyboard,
)
from bot.locales.loader import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, get_string
from bot.storage.users import (
    get_interface_language,
    get_onboarding_shown,
    set_interface_language,
    set_onboarding_shown,
)

router = Router(name="start")

_START_BUTTON_LABELS = frozenset(
    get_string("start_button_label", lang) for lang in SUPPORTED_LANGUAGES
)


async def _send_onboarding(message: Message, language: str) -> None:
    await message.answer(get_string("onboarding_capabilities", language))
    await message.answer(get_string("onboarding_settov", language))
    await message.answer(get_string("onboarding_quick_start", language))


@router.message(CommandStart())
@router.message(F.text.in_(_START_BUTTON_LABELS))
async def cmd_start(message: Message, db_path: str) -> None:
    telegram_id = message.from_user.id
    language = get_interface_language(db_path, telegram_id)
    if language is None:
        language_code = message.from_user.language_code
        language = language_code if language_code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
        set_interface_language(db_path, telegram_id, language)

    await message.answer(
        get_string("start_greeting", language),
        reply_markup=build_persistent_start_keyboard(language),
    )
    await message.answer(
        get_string("menu_intro", language),
        reply_markup=build_start_menu_keyboard(language),
    )

    if not get_onboarding_shown(db_path, telegram_id):
        await _send_onboarding(message, language)
        set_onboarding_shown(db_path, telegram_id, True)


@router.message(Command("help"))
async def cmd_help(message: Message, db_path: str) -> None:
    telegram_id = message.from_user.id
    language = get_interface_language(db_path, telegram_id)
    if language is None:
        language_code = message.from_user.language_code
        language = language_code if language_code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    await _send_onboarding(message, language)


@router.callback_query(F.data == CALLBACK_CAPABILITIES)
async def on_menu_capabilities(callback: CallbackQuery, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    await callback.message.answer(get_string("onboarding_capabilities", language))
    await callback.answer()


@router.callback_query(F.data == CALLBACK_CREATE_POST)
async def on_menu_create_post(callback: CallbackQuery, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    settings = load_settings()
    await callback.message.answer(
        get_string("menu_cta_button", language),
        reply_markup=build_create_post_keyboard(settings.mini_app_url, language),
    )
    await callback.answer()


@router.callback_query(F.data == CALLBACK_TEXT_HINT)
async def on_menu_text_hint(callback: CallbackQuery, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    await callback.message.answer(get_string("menu_text_generation_hint", language))
    await callback.answer()
