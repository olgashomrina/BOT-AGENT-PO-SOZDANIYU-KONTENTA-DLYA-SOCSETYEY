from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.config import load_settings
from bot.handlers.content import _AI_ERROR_KEYS, _resolve_language
from bot.keyboards.refine import build_refine_keyboard
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.services import content_generator, output_formatter
from bot.services.ai_gateway import AIGatewayError
from bot.services.content_generator import SHORTEN_INSTRUCTION
from bot.storage.limits import LimitStatus, check_limit_status, increment_usage
from bot.storage.whitelist import is_whitelisted

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="refine")


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
