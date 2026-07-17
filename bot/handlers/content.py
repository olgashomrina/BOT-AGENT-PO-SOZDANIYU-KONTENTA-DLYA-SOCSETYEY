from __future__ import annotations

import logging
import re
from typing import Literal

from aiogram import Bot, F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.keyboards.transcript_confirm import (
    CALLBACK_CONFIRM,
    CALLBACK_EDIT,
    build_transcript_confirm_keyboard,
)
from bot.locales.loader import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, get_string
from bot.logging_config import LOGGER_NAME
from bot.services import input_processor
from bot.services.ai_gateway import (
    AIGatewayError,
    AIGatewayInvalidResponseError,
    AIGatewayRateLimitError,
    AIGatewayTimeoutError,
    AIGatewayUnavailableError,
    TranscriptionError,
)
from bot.services.input_processor import LinkExtractionError
from bot.storage.users import get_content_language, get_interface_language

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="content")

_URL_PATTERN = re.compile(r"https?://\S+|www\.\S+")

InputType = Literal["link", "voice", "text"]

# AI Gateway network-level errors that can surface from transcribe(), mapped
# to the matching taxonomy message (Plan.md 5.2). AIGatewayError itself is
# the fallback for any future subclass not listed here explicitly.
_AI_ERROR_KEYS: dict[type[AIGatewayError], str] = {
    AIGatewayTimeoutError: "error_ai_timeout",
    AIGatewayRateLimitError: "error_rate_limit",
    AIGatewayUnavailableError: "error_ai_unavailable",
    AIGatewayInvalidResponseError: "error_invalid_ai_response",
}


class VoiceConfirmStates(StatesGroup):
    waiting_for_confirmation = State()
    waiting_for_edit = State()


def detect_input_type(message: Message) -> InputType:
    if message.voice is not None or message.audio is not None:
        return "voice"

    text = message.text or message.caption
    if text and _URL_PATTERN.search(text):
        return "link"

    entities = (message.entities or []) + (message.caption_entities or [])
    if any(entity.type in ("url", "text_link") for entity in entities):
        return "link"

    return "text"


def _resolve_language(db_path: str, telegram_id: int, language_code: str | None) -> str:
    language = get_interface_language(db_path, telegram_id)
    if language is None:
        language = language_code if language_code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
    return language


@router.message(StateFilter(None))
async def route_content(message: Message, db_path: str, bot: Bot, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    input_type = detect_input_type(message)

    if input_type == "text":
        await _finish(message, language, message.text, state)
        return

    if input_type == "link":
        await _handle_link(message, language, state)
        return

    await _handle_voice(message, db_path, bot, state, language)


async def _handle_link(message: Message, language: str, state: FSMContext) -> None:
    raw = message.text or message.caption or ""
    match = _URL_PATTERN.search(raw)
    url = match.group(0) if match else raw

    try:
        extracted_text = input_processor.extract_from_link(url)
    except LinkExtractionError:
        logger.warning("Link extraction failed", extra={"user_id": message.from_user.id, "operation": "extract_link"})
        await message.answer(get_string("error_link_extraction", language))
        return

    await _finish(message, language, extracted_text, state)


async def _handle_voice(
    message: Message, db_path: str, bot: Bot, state: FSMContext, language: str
) -> None:
    language_hint = get_content_language(db_path, message.from_user.id) or language

    try:
        transcript = await input_processor.handle_voice(bot, message, language_hint=language_hint)
    except TranscriptionError:
        logger.warning("Transcription failed", extra={"user_id": message.from_user.id, "operation": "transcribe"})
        await message.answer(get_string("error_transcription", language))
        return
    except AIGatewayError as exc:
        error_key = _AI_ERROR_KEYS.get(type(exc), "error_unexpected")
        logger.warning(
            "AI Gateway error during transcription",
            extra={"user_id": message.from_user.id, "operation": "transcribe", "error_class": type(exc).__name__},
        )
        await message.answer(get_string(error_key, language))
        return

    await _show_transcript_confirmation(message, language, transcript, state)


async def _show_transcript_confirmation(
    message: Message, language: str, transcript: str, state: FSMContext
) -> None:
    await state.update_data(transcript=transcript, language=language)
    await state.set_state(VoiceConfirmStates.waiting_for_confirmation)
    await message.answer(
        get_string("transcript_preview", language, text=transcript),
        reply_markup=build_transcript_confirm_keyboard(language),
    )


@router.callback_query(F.data == CALLBACK_CONFIRM, VoiceConfirmStates.waiting_for_confirmation)
async def on_transcript_confirm(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    transcript = data.get("transcript", "")
    language = data.get("language", DEFAULT_LANGUAGE)

    logger.info("Voice transcript confirmed", extra={"user_id": callback.from_user.id, "operation": "handler:content"})
    await _finish(callback.message, language, transcript, state)
    await callback.answer()


@router.callback_query(F.data == CALLBACK_EDIT, VoiceConfirmStates.waiting_for_confirmation)
async def on_transcript_edit_request(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    language = data.get("language", DEFAULT_LANGUAGE)
    await state.set_state(VoiceConfirmStates.waiting_for_edit)

    await callback.message.answer(get_string("transcript_edit_prompt", language))
    await callback.answer()


@router.message(VoiceConfirmStates.waiting_for_edit)
async def on_transcript_edited_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    language = data.get("language", DEFAULT_LANGUAGE)

    if not message.text:
        await message.answer(get_string("transcript_edit_prompt", language))
        return

    logger.info("Voice transcript edited, awaiting re-confirmation", extra={"user_id": message.from_user.id, "operation": "handler:content"})
    await _show_transcript_confirmation(message, language, message.text, state)


async def _finish(message: Message, language: str, text: str, state: FSMContext) -> None:
    # Phase 6 (Content Generator) will read this instead of the placeholder
    # reply below — stored now so the confirmed text isn't lost in the meantime.
    await state.set_data({"final_text": text})
    await state.set_state(None)
    logger.info(
        "Content ready for generation",
        extra={"user_id": message.from_user.id, "operation": "handler:content", "content_length": len(text)},
    )
    await message.answer(get_string("content_ready_stub", language))
