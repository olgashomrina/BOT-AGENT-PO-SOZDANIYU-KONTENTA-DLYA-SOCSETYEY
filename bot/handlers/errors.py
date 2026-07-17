from __future__ import annotations

import logging

from aiogram import Bot, Router
from aiogram.types import ErrorEvent

from bot.locales.loader import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, get_string
from bot.logging_config import LOGGER_NAME
from bot.storage.users import get_interface_language

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="errors")


def _extract_chat_context(event: ErrorEvent) -> tuple[int | None, int | None]:
    update = event.update
    message = update.message or update.edited_message
    if message is not None:
        telegram_id = message.from_user.id if message.from_user else None
        return message.chat.id, telegram_id

    callback = update.callback_query
    if callback is not None:
        chat_id = callback.message.chat.id if callback.message else None
        return chat_id, callback.from_user.id

    return None, None


def _resolve_update_type(event: ErrorEvent) -> str:
    try:
        return event.update.event_type
    except Exception:
        return "unknown"


@router.error()
async def handle_unexpected_error(event: ErrorEvent, db_path: str, bot: Bot) -> None:
    """Safety net for exceptions that escape local per-handler try/except
    blocks (bugs, unforeseen cases) — Plan.md Phase 8. Does NOT replace the
    specific AIGatewayError/LinkExtractionError/TranscriptionError catching
    already done in bot/handlers/content.py and bot/handlers/refine.py."""
    exc = event.exception
    update_type = _resolve_update_type(event)
    chat_id, telegram_id = _extract_chat_context(event)

    logger.error(
        "Unhandled exception in %s: %s",
        update_type,
        exc,
        exc_info=exc,
        extra={
            "user_id": telegram_id,
            "operation": f"handler:{update_type}",
            "error_class": type(exc).__name__,
            "error_message": str(exc),
        },
    )

    if chat_id is None:
        return

    language = get_interface_language(db_path, telegram_id) if telegram_id else None
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE

    await bot.send_message(chat_id, get_string("error_unexpected", language))
