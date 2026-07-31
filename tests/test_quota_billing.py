"""End-to-end quota accounting, fed through the real dispatcher.

Handler-level tests cannot see this: quota used to be charged by an outer
middleware, so calling a handler directly never exercised it at all. Every
test here goes through build_dispatcher() and feed_update, the same path a
real Telegram update takes.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, Message, Update, User

from bot.handlers.authorpost import AuthorPostStates
from bot.main import build_dispatcher
from bot.services import content_generator
from bot.storage.limits import get_daily_count, increment_usage
from bot.storage.style_examples import get_style_examples
from bot.storage.whitelist import add_user

TELEGRAM_ID = 111


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")


@pytest.fixture(autouse=True)
def _whitelisted(db_path):
    add_user(db_path, TELEGRAM_ID)


@pytest.fixture(autouse=True)
def _no_real_ai(monkeypatch):
    # Style analysis fires on the fifth sample (bot/handlers/style_reading.py).
    # It must never reach the network from a test, and it must not be what a
    # quota assertion is measuring either.
    monkeypatch.setattr(
        content_generator, "analyze_style", AsyncMock(return_value="• тон")
    )


def _make_bot() -> AsyncMock:
    bot = AsyncMock()
    # FSMContextMiddleware keys storage on bot.id, so it has to be a real,
    # stable value rather than an auto-generated Mock attribute.
    bot.id = 1
    return bot


def _make_update(update_id: int, text: str) -> Update:
    user = User(id=TELEGRAM_ID, is_bot=False, first_name="Test", language_code="ru")
    chat = Chat(id=TELEGRAM_ID, type="private")
    message = Message(
        message_id=update_id,
        date=datetime.now(timezone.utc),
        chat=chat,
        from_user=user,
        text=text,
    )
    return Update(update_id=update_id, message=message)


async def _send_samples(dispatcher, bot, db_path, count: int) -> None:
    state = dispatcher.fsm.get_context(bot, chat_id=TELEGRAM_ID, user_id=TELEGRAM_ID)
    await state.set_state(AuthorPostStates.collecting_examples)
    for index in range(count):
        await dispatcher.feed_update(
            bot, _make_update(index + 1, f"Образец {index}"), db_path=db_path
        )


@pytest.mark.asyncio
async def test_sending_style_samples_costs_no_quota(db_path):
    dispatcher = build_dispatcher()
    bot = _make_bot()

    await _send_samples(dispatcher, bot, db_path, 5)

    assert get_daily_count(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_every_sample_is_stored_even_with_the_daily_quota_used_up(db_path, monkeypatch):
    # The reported bug: the fifth sample was answered with "you have used your
    # daily limit" and dropped, because the four before it had each spent a
    # unit of a quota no AI call was ever made against.
    monkeypatch.setenv("DAILY_LIMIT", "4")
    for _ in range(4):
        increment_usage(db_path, TELEGRAM_ID)
    dispatcher = build_dispatcher()
    bot = _make_bot()

    await _send_samples(dispatcher, bot, db_path, 5)

    assert len(get_style_examples(db_path, TELEGRAM_ID)) == 5


@pytest.mark.asyncio
async def test_a_command_costs_no_quota(db_path):
    dispatcher = build_dispatcher()
    bot = _make_bot()

    await dispatcher.feed_update(bot, _make_update(1, "/help"), db_path=db_path)

    assert get_daily_count(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_a_text_post_costs_exactly_one_unit(db_path, monkeypatch):
    monkeypatch.setattr(
        content_generator,
        "generate_variants",
        AsyncMock(return_value=["вариант"]),
    )
    dispatcher = build_dispatcher()
    bot = _make_bot()

    await dispatcher.feed_update(
        bot, _make_update(1, "Напиши пост про кофе"), db_path=db_path
    )

    assert get_daily_count(db_path, TELEGRAM_ID) == 1
