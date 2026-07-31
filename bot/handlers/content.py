from __future__ import annotations

import logging
import re
from typing import Literal

from aiogram import Bot, F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.config import load_settings
from bot.keyboards.transcript_confirm import (
    CALLBACK_CONFIRM,
    CALLBACK_EDIT,
    build_transcript_confirm_keyboard,
)
from bot.keyboards.refine import build_refine_keyboard
from bot.locales.loader import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, get_string
from bot.logging_config import LOGGER_NAME
from bot.services import content_generator, cost_tracker, input_processor, output_formatter
from bot.services.ai_gateway import (
    AIGatewayError,
    AIGatewayInvalidResponseError,
    AIGatewayOutOfBudgetError,
    AIGatewayRateLimitError,
    AIGatewayTimeoutError,
    AIGatewayUnavailableError,
    TranscriptionError,
)
from bot.services.input_processor import LinkExtractionError
from bot.storage.costs import record_cost
from bot.handlers.guards import check_message_limit_or_reply
from bot.storage.limits import increment_usage
from bot.storage.refine_context import save_refine_context
from bot.storage.style_examples import get_style_examples
from bot.storage.users import (
    clear_pending_media,
    get_content_language,
    get_interface_language,
    get_pending_media,
    set_pending_media,
)

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
    AIGatewayOutOfBudgetError: "error_out_of_budget",
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


@router.message(Command("clear_media"))
async def cmd_clear_media(message: Message, db_path: str) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    had_pending_media = get_pending_media(db_path, telegram_id) is not None
    clear_pending_media(db_path, telegram_id)

    message_key = "media_cleared_confirmation" if had_pending_media else "media_nothing_to_clear"
    await message.answer(get_string(message_key, language))


async def _handle_media_attachment(
    message: Message, db_path: str, telegram_id: int, language: str
) -> None:
    if message.photo:
        file_id = message.photo[-1].file_id
        media_type = "photo"
    else:
        file_id = message.video.file_id
        media_type = "video"

    set_pending_media(db_path, telegram_id, file_id, media_type)
    await message.answer(get_string("media_attached_confirmation", language))
    logger.info(
        "Media attached for next channel publish",
        extra={"user_id": telegram_id, "operation": "handler:content", "media_type": media_type},
    )


@router.message(StateFilter(None))
async def route_content(message: Message, db_path: str, bot: Bot, state: FSMContext) -> None:
    telegram_id = message.from_user.id
    language = _resolve_language(db_path, telegram_id, message.from_user.language_code)

    # Checked before detect_input_type: a photo/video message (even with a
    # caption) is always treated as a media attachment for the next channel
    # publish, never as link/voice/text content input — detect_input_type
    # has no "photo"/"video" branch and would otherwise misclassify a
    # captioned photo as link or text content.
    if message.photo or message.video:
        await _handle_media_attachment(message, db_path, telegram_id, language)
        return

    # Quota is checked once here, for every branch below: text and link both
    # end in a generation, voice ends in a paid transcription. Everything
    # that returned above this line stays free, and so does every
    # state-filtered handler that never reaches route_content at all —
    # style samples among them, which is the bug this placement fixes.
    if not await check_message_limit_or_reply(message, db_path, language):
        return

    input_type = detect_input_type(message)

    if input_type == "text":
        await _finish(message, language, message.text, state, telegram_id, db_path, bill=True)
        return

    if input_type == "link":
        await _handle_link(message, language, state, telegram_id, db_path)
        return

    await _handle_voice(message, db_path, bot, state, language)


async def _handle_link(
    message: Message, language: str, state: FSMContext, telegram_id: int, db_path: str
) -> None:
    raw = message.text or message.caption or ""
    match = _URL_PATTERN.search(raw)
    url = match.group(0) if match else raw

    try:
        extracted_text = input_processor.extract_from_link(url)
    except LinkExtractionError:
        logger.warning("Link extraction failed", extra={"user_id": message.from_user.id, "operation": "extract_link"})
        await message.answer(get_string("error_link_extraction", language))
        return

    await _finish(message, language, extracted_text, state, telegram_id, db_path, bill=True)


async def _reject_overlong_voice(message: Message, language: str) -> bool:
    """Refuse recordings above the configured length and report it.

    Transcription is billed per second of audio (see dengi.md), so the check
    happens before the file is even downloaded — a rejected voice message
    costs nothing. Returns True when the message was rejected.
    """
    limit_seconds = load_settings().max_voice_duration_seconds
    duration = (message.voice or message.audio).duration

    if duration <= limit_seconds:
        return False

    logger.info(
        "Voice message rejected as too long",
        extra={
            "user_id": message.from_user.id,
            "operation": "handler:content",
            "duration_seconds": duration,
            "limit_seconds": limit_seconds,
        },
    )
    await message.answer(
        get_string(
            "error_voice_too_long",
            language,
            # Whole minutes read better than seconds in the user-facing text;
            # limits below a minute still round up to "1 min" rather than "0".
            limit_minutes=max(1, round(limit_seconds / 60)),
        )
    )
    return True


async def _handle_voice(
    message: Message, db_path: str, bot: Bot, state: FSMContext, language: str
) -> None:
    if await _reject_overlong_voice(message, language):
        return

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

    settings = load_settings()
    record_cost(
        db_path,
        message.from_user.id,
        "transcribe",
        settings.ai_gateway_transcription_model,
        cost_tracker.transcription_cost(
            settings.ai_gateway_transcription_model,
            (message.voice or message.audio).duration,
        ),
    )

    increment_usage(db_path, message.from_user.id)

    await _show_transcript_confirmation(message, language, transcript, state)


async def _show_transcript_confirmation(
    message: Message, language: str, transcript: str, state: FSMContext
) -> None:
    await state.update_data(transcript=transcript, language=language)
    await state.set_state (VoiceConfirmStates.waiting_for_confirmation)
    await message.answer(
        get_string("transcript_preview", language, text=transcript),
        reply_markup=build_transcript_confirm_keyboard(language),
    )


@router.callback_query(F.data == CALLBACK_CONFIRM, VoiceConfirmStates.waiting_for_confirmation)
async def on_transcript_confirm(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    data = await state.get_data()
    transcript = data.get("transcript", "")
    language = data.get("language", DEFAULT_LANGUAGE)

    logger.info("Voice transcript confirmed", extra={"user_id": callback.from_user.id, "operation": "handler:content"})
    await _finish(
        callback.message,
        language,
        transcript,
        state,
        callback.from_user.id,
        db_path,
        bill=False,
    )
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


# Public because bot/handlers/authorpost.py sends its variants through the
# same path — same formatting, same refine keyboard — and duplicating this
# there would let the two output formats drift apart.
async def send_variants(
    message: Message,
    language: str,
    platform: str,
    variants: list[str],
    db_path: str,
    source_text: str,
    content_language: str,
    with_hashtags: bool,
) -> None:
    for index, variant in enumerate(variants, start=1):
        # WHY the sent message is captured and recorded: the refine buttons
        # attached below regenerate from the source of THIS post. Telegram
        # keeps old messages and their buttons alive indefinitely, so a single
        # shared per-chat value would be overwritten by the next generation and
        # a later tap would regenerate the wrong thing entirely.
        sent = await message.answer(
            output_formatter.format_variant(variant),
            parse_mode=output_formatter.PARSE_MODE,
            reply_markup=build_refine_keyboard(platform, index, language),
        )
        save_refine_context(
            db_path,
            message.chat.id,
            sent.message_id,
            source_text,
            content_language,
            with_hashtags,
            platform,
        )


async def _finish(
    message: Message,
    language: str,
    text: str,
    state: FSMContext,
    telegram_id: int,
    db_path: str,
    bill: bool,
) -> None:
    content_language = get_content_language(db_path, telegram_id) or language
    # Keep FSM state itself at None (route_content's StateFilter(None) needs
    # this to match again for the next message) while still holding data —
    # MemoryStorage (and every other aiogram storage backend) keeps state and
    # data as independent fields, so this is safe.
    #
    # What still reads these keys, so nobody deletes them as dead: `language`
    # is read by the refine callbacks (bot/handlers/refine.py) to pick the
    # interface language for their replies, and `content_language` is read by
    # bot/handlers/authorpost.py as its first choice when deciding what
    # language to write an authored post in.
    #
    # What does NOT read them: the refine callbacks no longer take the post's
    # source or its hashtag setting from here. Those are per-message now
    # (bot/storage/refine_context.py) — FSM data is per chat, so the next
    # generation overwrote it and a tap on an older post regenerated the
    # wrong thing entirely. Do not reintroduce a `with_hashtags` key here.
    await state.update_data(
        source_text=text,
        content_language=content_language,
        language=language,
    )
    await state.set_state(None)
    logger.info(
        "Content ready for generation",
        extra={"user_id": telegram_id, "operation": "handler:content", "content_length": len(text)},
    )

    settings = load_settings()
    style_examples = get_style_examples(db_path, telegram_id)

    try:
        telegram_variants = await content_generator.generate_variants(
            text,
            "telegram",
            content_language,
            count=settings.content_variants_count,
            style_examples=style_examples,
        )
        vk_variants = await content_generator.generate_variants(
            text,
            "vk",
            content_language,
            count=settings.content_variants_count,
            style_examples=style_examples,
        )
    except AIGatewayError as exc:
        error_key = _AI_ERROR_KEYS.get(type(exc), "error_unexpected")
        logger.warning(
            "AI Gateway error during content generation",
            extra={"user_id": telegram_id, "operation": "generate_variants", "error_class": type(exc).__name__},
        )
        await message.answer(get_string(error_key, language))
        return

    # Charged after the calls succeeded, like bot/handlers/refine.py: a
    # failed generation costs the user nothing. `bill` is False on the
    # voice path — _handle_voice already charged for that request when it
    # paid for the transcription, and charging again here would make a
    # voice post cost twice what the same post costs as text.
    if bill:
        increment_usage(db_path, telegram_id)

    await send_variants(
        message,
        language,
        "telegram",
        telegram_variants,
        db_path=db_path,
        source_text=text,
        content_language=content_language,
        with_hashtags=False,
    )
    await send_variants(
        message,
        language,
        "vk",
        vk_variants,
        db_path=db_path,
        source_text=text,
        content_language=content_language,
        with_hashtags=False,
    )
