from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.locales.loader import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, get_string
from bot.storage.limits import increment_usage, is_within_limit
from bot.storage.users import get_interface_language


class RateLimitMiddleware(BaseMiddleware):
    """Register via dispatcher.message.outer_middleware — scoped to Message events only."""

    def __init__(self, daily_limit: int, monthly_limit: int) -> None:
        self._daily_limit = daily_limit
        self._monthly_limit = monthly_limit

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        db_path = data["db_path"]
        telegram_id = event.from_user.id

        if not is_within_limit(db_path, telegram_id, self._daily_limit, self._monthly_limit):
            language = get_interface_language(db_path, telegram_id)
            if language is None:
                language_code = event.from_user.language_code
                language = (
                    language_code if language_code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
                )
            await event.answer(get_string("error_limit_exceeded", language))
            return None

        increment_usage(db_path, telegram_id)
        return await handler(event, data)
