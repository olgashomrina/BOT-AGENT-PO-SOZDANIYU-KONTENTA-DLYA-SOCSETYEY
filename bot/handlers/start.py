from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.config import load_settings
from bot.handlers.content import _AI_ERROR_KEYS, _resolve_language
from bot.handlers.refine import _check_whitelist_or_reply
from bot.keyboards.start import (
    CALLBACK_CAPABILITIES,
    CALLBACK_CREATE_POST,
    CALLBACK_PHOTO_GEN,
    CALLBACK_TEXT_HINT,
    build_create_post_keyboard,
    build_persistent_start_keyboard,
    build_start_menu_keyboard,
)
from bot.locales.loader import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, get_string
from bot.logging_config import LOGGER_NAME
from bot.services import ai_gateway, content_generator
from bot.services.ai_gateway import AIGatewayError
from bot.storage.users import (
    get_interface_language,
    get_onboarding_shown,
    set_interface_language,
    set_onboarding_shown,
    set_pending_media,
)

router = Router(name="start")

logger = logging.getLogger(LOGGER_NAME)


class PhotoGenStates(StatesGroup):
    waiting_for_description = State()


_START_BUTTON_LABELS = frozenset(
    get_string("start_button_label", lang) for lang in SUPPORTED_LANGUAGES
)


async def _send_onboarding(message: Message, language: str) -> None:
    await message.answer(get_string("onboarding_capabilities", language))
    await message.answer(get_string("onboarding_settov", language))
    await message.answer(get_string("onboarding_quick_start", language))


@router.message(CommandStart())
@router.message(F.text.in_(_START_BUTTON_LABELS))
async def cmd_start(message: Message, state: FSMContext, db_path: str) -> None:
    await state.set_state(None)
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


@router.callback_query(F.data == CALLBACK_PHOTO_GEN)
async def on_menu_photo_gen(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    telegram_id = callback.from_user.id
    language = _resolve_language(db_path, telegram_id, callback.from_user.language_code)

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    await state.update_data(language=language)
    await state.set_state(PhotoGenStates.waiting_for_description)
    await callback.message.answer(get_string("photo_gen_prompt", language))
    await callback.answer()


@router.message(PhotoGenStates.waiting_for_description)
async def on_photo_gen_description(
    message: Message, state: FSMContext, db_path: str, bot: Bot
) -> None:
    telegram_id = message.from_user.id
    data = await state.get_data()
    language = data.get("language") or _resolve_language(
        db_path, telegram_id, message.from_user.language_code
    )
    description = message.text or ""

    if not description:
        await message.answer(get_string("photo_gen_prompt", language))
        return

    try:
        image_prompt = await content_generator.generate_image_prompt(description)
        image_bytes = await ai_gateway.generate_image(image_prompt)
    except AIGatewayError as exc:
        error_key = _AI_ERROR_KEYS.get(type(exc), "error_unexpected")
        logger.warning(
            "AI Gateway error during standalone image generation",
            extra={"user_id": telegram_id, "operation": "photo_gen", "error_class": type(exc).__name__},
        )
        await message.answer(get_string(error_key, language))
        return

    try:
        sent_message = await bot.send_photo(
            message.chat.id,
            photo=BufferedInputFile(image_bytes, filename="ai_image.png"),
            caption=get_string("image_preview_caption", language),
        )
    except TelegramAPIError:
        logger.warning(
            "Failed to deliver standalone generated image to user",
            extra={"user_id": telegram_id, "operation": "photo_gen"},
        )
        await message.answer(get_string("image_delivery_failed", language))
        return

    file_id = sent_message.photo[-1].file_id
    set_pending_media(db_path, telegram_id, file_id, "photo")
    await state.set_state(None)
    await message.answer(get_string("photo_gen_ready", language))
