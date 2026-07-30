"""Daily image budget guard, shared by every handler that generates images.

Images dominate the bot's running cost — 3.90 ₽ for the budget model and
~10–15 ₽ for `img-flux/pro1.1`, against ~0.25 ₽ for a post's text and
~0.96 ₽ per minute of transcription (see dengi.md). The general daily quota
in `RateLimitMiddleware` counts every request equally, so it cannot stop a
handful of taps on the picture buttons from draining the AI-proxy balance.

This module keeps that single rule in one place: `ensure_image_budget` is
called before any billed image call, `increment_image_usage` after one
succeeds. It takes a bare `answer` callable rather than a Message or
CallbackQuery so both the message-driven (`/start` photo generation) and
callback-driven (refine buttons) paths use exactly the same rule.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from bot.config import load_settings
from bot.locales.loader import get_string
from bot.logging_config import LOGGER_NAME
from bot.storage.limits import is_image_limit_reached

logger = logging.getLogger(LOGGER_NAME)

AnswerFn = Callable[..., Awaitable[Any]]


async def ensure_image_budget(
    answer: AnswerFn, db_path: str, telegram_id: int, language: str
) -> bool:
    """Whether this user may still generate an image today.

    On refusal the user is told (in their language) and False is returned, so
    the caller can bail out before spending anything.
    """
    limit = load_settings().daily_image_limit

    if not is_image_limit_reached(db_path, telegram_id, limit):
        return True

    logger.info(
        "Image generation refused: daily image budget spent",
        extra={
            "user_id": telegram_id,
            "operation": "image_budget",
            "daily_image_limit": limit,
        },
    )
    await answer(get_string("error_daily_image_limit", language, limit=limit))
    return False
