from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from bot.locales.loader import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, get_string
from bot.storage.users import get_interface_language
from bot.storage.whitelist import is_whitelisted


class WhitelistMiddleware(BaseMiddleware):
    """Register via dispatcher.message.outer_middleware — scoped to Message events only."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        db_path = data["db_path"]
        telegram_id = event.from_user.id

        if is_whitelisted(db_path, telegram_id):
            return await handler(event, data)

        language = get_interface_language(db_path, telegram_id)
        if language is None:
            language_code = event.from_user.language_code
            language = language_code if language_code in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE
        await event.answer(get_string("error_not_whitelisted", language))
        return None
