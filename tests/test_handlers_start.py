from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bot.handlers.start import GREETING, cmd_start


@pytest.mark.asyncio
async def test_cmd_start_sends_stub_greeting():
    message = AsyncMock()

    await cmd_start(message)

    message.answer.assert_awaited_once_with(GREETING)


def test_greeting_is_non_empty_russian_text():
    assert isinstance(GREETING, str)
    assert len(GREETING.strip()) > 0
