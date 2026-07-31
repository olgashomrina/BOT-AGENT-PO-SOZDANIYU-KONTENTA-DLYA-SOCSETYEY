from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, Message

from bot.config import load_settings
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.storage.limits import LimitStatus, check_limit_status
from bot.storage.whitelist import is_whitelisted

logger = logging.getLogger(LOGGER_NAME)


async def safe_answer(callback: CallbackQuery) -> None:
    # Telegram invalidates a callback query once too much time passes before
    # it's acknowledged — observed in production after a slow/retried AI
    # Gateway call ("query is too old and response timeout expired"). By the
    # time we get here the substantive reply has already been sent via
    # callback.message.answer()/send_photo, so answering the callback itself
    # only stops the button's loading spinner — safe to ignore if it fails.
    try:
        await callback.answer()
    except TelegramBadRequest as exc:
        logger.warning(
            "Callback query answer failed (likely stale)",
            extra={"error_message": str(exc)},
        )


async def check_whitelist_or_reply(
    callback: CallbackQuery, db_path: str, language: str
) -> bool:
    # WHY this check exists at all: WhitelistMiddleware (bot/middlewares/
    # whitelist_middleware.py) is registered only on dispatcher.message.outer_
    # middleware (see bot/main.py) — it never runs for callback_query events.
    if is_whitelisted(db_path, callback.from_user.id):
        return True

    await callback.message.answer(get_string("error_not_whitelisted", language))
    await safe_answer(callback)
    return False


def _limit_error_key(db_path: str, telegram_id: int) -> str | None:
    """The locale key to answer with, or None when the user is under quota."""
    settings = load_settings()
    status = check_limit_status(
        db_path, telegram_id, settings.daily_limit, settings.monthly_limit
    )
    if status is LimitStatus.OK:
        return None
    return (
        "error_daily_limit_exceeded"
        if status is LimitStatus.DAILY_EXCEEDED
        else "error_monthly_limit_exceeded"
    )


async def check_limit_or_reply(
    callback: CallbackQuery, db_path: str, language: str
) -> bool:
    # Quota is checked (and charged) at each paid AI call rather than centrally,
    # so every handler that is about to spend one has to ask first. Without it,
    # button-driven generations would call the AI Gateway for free, unlimited.
    message_key = _limit_error_key(db_path, callback.from_user.id)
    if message_key is None:
        return True

    await callback.message.answer(get_string(message_key, language))
    await safe_answer(callback)
    return False


async def check_message_limit_or_reply(
    message: Message, db_path: str, language: str
) -> bool:
    # The Message twin of check_limit_or_reply: three paid calls are reached
    # from a plain message rather than from a button (bot/handlers/content.py,
    # bot/handlers/start.py).
    message_key = _limit_error_key(db_path, message.from_user.id)
    if message_key is None:
        return True

    await message.answer(get_string(message_key, language))
    return False
