from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from bot.services.owner_notifier import notify_owner

OWNER_CHAT_ID = 999


@pytest.mark.asyncio
async def test_notify_owner_sends_message():
    bot = AsyncMock()

    await notify_owner(bot, OWNER_CHAT_ID, "Бот упал, нужна помощь.")

    bot.send_message.assert_awaited_once_with(OWNER_CHAT_ID, "Бот упал, нужна помощь.")


@pytest.mark.asyncio
async def test_notify_owner_does_not_raise_when_send_fails(caplog):
    bot = AsyncMock()
    bot.send_message = AsyncMock(side_effect=RuntimeError("owner blocked the bot"))

    # Attach caplog's handler directly rather than relying on propagation to
    # the root logger: bot/logging_config.py's setup_logging() sets
    # propagate=False on the "bot" logger, and once any test in the suite
    # calls it for real, that setting sticks for the rest of the process.
    logger = logging.getLogger("bot")
    previous_propagate = logger.propagate
    logger.propagate = False
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger="bot"):
            await notify_owner(bot, OWNER_CHAT_ID, "Бот упал, нужна помощь.")
    finally:
        logger.removeHandler(caplog.handler)
        logger.propagate = previous_propagate

    assert any("Failed to notify owner" in record.message for record in caplog.records)
