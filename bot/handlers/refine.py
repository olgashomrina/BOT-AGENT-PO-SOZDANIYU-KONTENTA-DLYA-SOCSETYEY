from __future__ import annotations

import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.config import load_settings
from bot.handlers.content import _AI_ERROR_KEYS, _resolve_language
from bot.keyboards.refine import build_refine_keyboard
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.services import ai_gateway, content_generator, output_formatter
from bot.services.ai_gateway import AIGatewayError
from bot.services.content_generator import SHORTEN_INSTRUCTION
from bot.storage.limits import LimitStatus, check_limit_status, increment_usage
from bot.storage.users import clear_pending_media, get_channel_id, get_pending_media, set_pending_media
from bot.storage.whitelist import is_whitelisted

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="refine")

# Telegram's hard limit for photo/video captions (Bot API "caption" field),
# well below the 4096-char limit for plain send_message text. AI-generated
# variant text is written for send_message and can plausibly exceed this
# when a photo/video is attached, so publishing must not crash on it.
_TELEGRAM_CAPTION_LIMIT = 1024


def _truncate_caption(text: str) -> str:
    if len(text) <= _TELEGRAM_CAPTION_LIMIT:
        return text
    return text[: _TELEGRAM_CAPTION_LIMIT - 1] + "…"


async def _check_whitelist_or_reply(callback: CallbackQuery, db_path: str, language: str) -> bool:
    # WHY this check exists here at all: WhitelistMiddleware (bot/middlewares/
    # whitelist_middleware.py) is registered only on dispatcher.message.outer_
    # middleware (see bot/main.py) — it never runs for callback_query events.
    telegram_id = callback.from_user.id
    if is_whitelisted(db_path, telegram_id):
        return True

    await callback.message.answer(get_string("error_not_whitelisted", language))
    await callback.answer()
    return False


async def _check_limit_or_reply(callback: CallbackQuery, db_path: str, language: str) -> bool:
    # WHY this check exists here at all: RateLimitMiddleware (bot/middlewares/
    # rate_limit_middleware.py) is registered only on dispatcher.message.outer_
    # middleware (see bot/main.py) — it never runs for callback_query events.
    # Without an explicit check in every refine handler, "Ещё вариант"/
    # "Короче" clicks would call the AI Gateway for free, unlimited, bypassing
    # the daily/monthly quota entirely. This mirrors the middleware's own
    # check + reply + (on success) increment logic.
    settings = load_settings()
    telegram_id = callback.from_user.id
    status = check_limit_status(db_path, telegram_id, settings.daily_limit, settings.monthly_limit)
    if status is LimitStatus.OK:
        return True

    message_key = (
        "error_daily_limit_exceeded"
        if status is LimitStatus.DAILY_EXCEEDED
        else "error_monthly_limit_exceeded"
    )
    await callback.message.answer(get_string(message_key, language))
    await callback.answer()
    return False


async def _generate_and_send(
    callback: CallbackQuery,
    state: FSMContext,
    db_path: str,
    platform: str,
    extra_instruction: str | None,
) -> None:
    telegram_id = callback.from_user.id
    data = await state.get_data()
    language = data.get("language") or _resolve_language(
        db_path, telegram_id, callback.from_user.language_code
    )

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    if not await _check_limit_or_reply(callback, db_path, language):
        return

    source_text = data.get("source_text")
    content_language = data.get("content_language")
    if not source_text or not content_language:
        await callback.message.answer(get_string("error_refine_missing_context", language))
        await callback.answer()
        return

    try:
        variants = await content_generator.generate_variants(
            source_text, platform, content_language, count=1, extra_instruction=extra_instruction
        )
    except AIGatewayError as exc:
        error_key = _AI_ERROR_KEYS.get(type(exc), "error_unexpected")
        logger.warning(
            "AI Gateway error during refine",
            extra={"user_id": telegram_id, "operation": "refine_generate", "error_class": type(exc).__name__},
        )
        await callback.message.answer(get_string(error_key, language))
        await callback.answer()
        return

    increment_usage(db_path, telegram_id)

    variant = variants[0]
    await callback.message.answer(
        output_formatter.format_variant(variant),
        parse_mode=output_formatter.PARSE_MODE,
        reply_markup=build_refine_keyboard(platform, 1, language),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("refine:more:"))
async def on_refine_more(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    platform = callback.data.split(":")[2]
    await _generate_and_send(callback, state, db_path, platform, extra_instruction=None)


@router.callback_query(F.data.startswith("refine:shorten:"))
async def on_refine_shorten(callback: CallbackQuery, state: FSMContext, db_path: str) -> None:
    platform = callback.data.split(":")[2]
    await _generate_and_send(callback, state, db_path, platform, extra_instruction=SHORTEN_INSTRUCTION)


@router.callback_query(F.data.startswith("refine:publish:"))
async def on_refine_publish(callback: CallbackQuery, state: FSMContext, db_path: str, bot: Bot) -> None:
    telegram_id = callback.from_user.id
    data = await state.get_data()
    language = data.get("language") or _resolve_language(
        db_path, telegram_id, callback.from_user.language_code
    )

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    channel_id = get_channel_id(db_path, telegram_id)
    if channel_id is None:
        await callback.message.answer(get_string("publish_no_channel_configured", language))
        await callback.answer()
        return

    # WHY read the text off callback.message rather than re-deriving it from
    # FSM data: the publish button is attached to one already-generated,
    # already-shown variant message specifically — FSM data (source_text)
    # only ever holds the original input used to (re)generate variants, not
    # any individual variant's text (see _generate_and_send above), and
    # there can be several variant messages in the chat at once. The exact
    # text the user approved is the text of the message the button sits
    # under, sent earlier via output_formatter.format_variant() with HTML
    # parse_mode; since that formatting only escapes &/</>, Telegram hands
    # the plain (unescaped) variant text straight back as callback.message.text.
    variant_text = callback.message.text or ""
    formatted_text = output_formatter.format_variant(variant_text)
    pending_media = get_pending_media(db_path, telegram_id)

    try:
        if pending_media is None:
            await bot.send_message(channel_id, formatted_text, parse_mode=output_formatter.PARSE_MODE)
        else:
            file_id, media_type = pending_media
            caption = _truncate_caption(formatted_text)
            if media_type == "photo":
                await bot.send_photo(
                    channel_id, photo=file_id, caption=caption, parse_mode=output_formatter.PARSE_MODE
                )
            else:
                await bot.send_video(
                    channel_id, video=file_id, caption=caption, parse_mode=output_formatter.PARSE_MODE
                )
    except TelegramAPIError:
        logger.warning(
            "Failed to publish variant to channel",
            extra={"user_id": telegram_id, "operation": "publish_to_channel"},
        )
        await callback.message.answer(get_string("publish_failed", language))
        await callback.answer()
        return

    if pending_media is not None:
        # Single-slot attachment is one-shot: media_attached_confirmation
        # tells the user it applies to "the next channel publish" only, so a
        # successful publish must consume it — otherwise an old photo would
        # silently keep attaching itself to every unrelated post afterward.
        clear_pending_media(db_path, telegram_id)

    await callback.message.answer(get_string("publish_success", language))
    await callback.answer()


@router.callback_query(F.data.startswith("refine:image:"))
async def on_refine_image(callback: CallbackQuery, state: FSMContext, db_path: str, bot: Bot) -> None:
    telegram_id = callback.from_user.id
    data = await state.get_data()
    language = data.get("language") or _resolve_language(
        db_path, telegram_id, callback.from_user.language_code
    )

    if not await _check_whitelist_or_reply(callback, db_path, language):
        return

    if not await _check_limit_or_reply(callback, db_path, language):
        return

    # WHY read the text off callback.message rather than FSM data: same
    # reasoning as on_refine_publish above — the image button sits under one
    # already-generated variant message specifically, and that message's
    # text is the exact post this image should illustrate.
    post_text = callback.message.text or ""

    try:
        image_prompt = await content_generator.generate_image_prompt(post_text)
        image_url = await ai_gateway.generate_image(image_prompt)
    except AIGatewayError as exc:
        error_key = _AI_ERROR_KEYS.get(type(exc), "error_unexpected")
        logger.warning(
            "AI Gateway error during image generation",
            extra={"user_id": telegram_id, "operation": "generate_image", "error_class": type(exc).__name__},
        )
        await callback.message.answer(get_string(error_key, language))
        await callback.answer()
        return

    try:
        sent_message = await bot.send_photo(
            callback.message.chat.id,
            photo=image_url,
            caption=get_string("image_preview_caption", language),
        )
    except TelegramAPIError:
        logger.warning(
            "Failed to deliver generated image to user",
            extra={"user_id": telegram_id, "operation": "generate_image"},
        )
        await callback.message.answer(get_string("image_delivery_failed", language))
        await callback.answer()
        return

    increment_usage(db_path, telegram_id)

    # WHY store Telegram's own file_id instead of the vendor image URL:
    # AI-provider-hosted image URLs are often time-limited, but once
    # Telegram has ingested the image into a sent message, its own file_id
    # is durable — using it (not the raw vendor URL) as what gets stored
    # here avoids the attachment silently breaking if the user publishes to
    # their channel later than the URL's expiry window.
    file_id = sent_message.photo[-1].file_id
    set_pending_media(db_path, telegram_id, file_id, "photo")

    await callback.message.answer(get_string("image_attached_confirmation", language))
    await callback.answer()
