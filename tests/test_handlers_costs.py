from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers.costs import cmd_costs
from bot.storage.costs import record_cost

OWNER_ID = 42
OTHER_ID = 111


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", str(OWNER_ID))


def _make_message(telegram_id: int):
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=telegram_id, language_code="ru")
    return message


@pytest.mark.asyncio
async def test_non_owner_is_refused(db_path):
    record_cost(db_path, OTHER_ID, "generate_image", "m", 3.90)
    message = _make_message(OTHER_ID)

    await cmd_costs(message, db_path)

    text = message.answer.await_args.args[0]
    assert "только владельцу" in text
    # No spend figures may leak to a non-owner.
    assert "3.90" not in text


@pytest.mark.asyncio
async def test_owner_sees_a_placeholder_when_nothing_was_spent(db_path):
    message = _make_message(OWNER_ID)

    await cmd_costs(message, db_path)

    assert "пока не записано" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_owner_sees_total_split_by_operation_and_user(db_path):
    record_cost(db_path, OTHER_ID, "generate_image", "img-flux/flux-2-klein-4b", 3.90)
    record_cost(db_path, OTHER_ID, "generate_image", "img-flux/flux-2-klein-4b", 3.90)
    record_cost(db_path, 222, "transcribe", "stt-openai/gpt-4o-mini-transcribe", 0.96)
    message = _make_message(OWNER_ID)

    await cmd_costs(message, db_path)

    text = message.answer.await_args.args[0]
    assert "8.76" in text  # 3.90 + 3.90 + 0.96
    assert "generate_image" in text
    assert "transcribe" in text
    assert str(OTHER_ID) in text
    assert "222" in text


@pytest.mark.asyncio
async def test_report_states_that_post_text_is_not_counted(db_path):
    record_cost(db_path, OTHER_ID, "generate_image", "m", 3.90)
    message = _make_message(OWNER_ID)

    await cmd_costs(message, db_path)

    # The owner is going to price a subscription off these numbers, so the
    # known gap has to be stated in the report itself.
    assert "Текст постов не учитывается" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_long_user_list_is_truncated(db_path):
    for telegram_id in range(1000, 1020):
        record_cost(db_path, telegram_id, "generate_image", "m", 3.90)
    message = _make_message(OWNER_ID)

    await cmd_costs(message, db_path)

    text = message.answer.await_args.args[0]
    assert "и ещё 5" in text
