from __future__ import annotations

import logging

from aiogram import Bot

from bot.logging_config import LOGGER_NAME

logger = logging.getLogger(LOGGER_NAME)


async def notify_owner(bot: Bot, owner_chat_id: int, message: str) -> None:
    """Best-effort notification to the bot owner's chat. Never raises —
    if the send itself fails (owner blocked the bot, network down), there
    is nowhere further to escalate to, so we log and move on."""
    try:
        await bot.send_message(owner_chat_id, message)
    except Exception as exc:
        logger.error(
            "Failed to notify owner: %s",
            exc,
            exc_info=True,
            extra={
                "operation": "notify_owner",
                "error_class": type(exc).__name__,
                "error_message": str(exc),
            },
        )
