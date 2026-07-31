from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.handlers.style_reading import REQUIRED_EXAMPLES, read_style_if_ready
from bot.locales.loader import get_string
from bot.services import content_generator
from bot.services.ai_gateway import AIGatewayTimeoutError
from bot.storage.limits import get_daily_count
from bot.storage.style_examples import add_style_example
from bot.storage.style_profile import get_style_profile, set_style_profile

TELEGRAM_ID = 111
SUMMARY = "• короткие абзацы\n• на «ты»"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("BOT_TOKEN", "123456:test-token")
    monkeypatch.setenv("AI_PROXY_API_KEY", "test-ai-key")
    monkeypatch.setenv("OWNER_CHAT_ID", "42")


def _make_message():
    message = AsyncMock()
    message.from_user = SimpleNamespace(id=TELEGRAM_ID, language_code="ru")
    return message


def _seed_examples(db_path, count):
    for index in range(count):
        add_style_example(db_path, TELEGRAM_ID, f"Образец {index}")


def _mock_analyze(monkeypatch, summary=SUMMARY):
    mock = AsyncMock(return_value=summary)
    monkeypatch.setattr(content_generator, "analyze_style", mock)
    return mock


def _enough_message(count):
    return get_string(
        "authorpost_samples_enough",
        "ru",
        count=count,
        required=REQUIRED_EXAMPLES,
    )


@pytest.mark.asyncio
async def test_below_the_threshold_nothing_happens(db_path, monkeypatch):
    analyze = _mock_analyze(monkeypatch)
    _seed_examples(db_path, REQUIRED_EXAMPLES - 1)
    message = _make_message()

    handled = await read_style_if_ready(message, db_path, TELEGRAM_ID, "ru", False)

    assert handled is False
    analyze.assert_not_awaited()
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_at_the_threshold_reads_and_saves_the_profile(db_path, monkeypatch):
    analyze = _mock_analyze(monkeypatch)
    _seed_examples(db_path, REQUIRED_EXAMPLES)
    message = _make_message()

    handled = await read_style_if_ready(message, db_path, TELEGRAM_ID, "ru", False)

    assert handled is True
    analyze.assert_awaited_once()
    assert get_style_profile(db_path, TELEGRAM_ID) == SUMMARY
    args, kwargs = message.answer.call_args
    assert args[0] == get_string("style_read_summary", "ru", summary=SUMMARY)
    assert kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_an_extra_sample_does_not_re_analyse(db_path, monkeypatch):
    analyze = _mock_analyze(monkeypatch)
    _seed_examples(db_path, REQUIRED_EXAMPLES)
    await read_style_if_ready(_make_message(), db_path, TELEGRAM_ID, "ru", False)
    analyze.reset_mock()

    add_style_example(db_path, TELEGRAM_ID, "Шестой образец")
    message = _make_message()
    handled = await read_style_if_ready(message, db_path, TELEGRAM_ID, "ru", False)

    assert handled is True
    analyze.assert_not_awaited()
    args, _ = message.answer.call_args
    assert args[0] == _enough_message(REQUIRED_EXAMPLES + 1)


@pytest.mark.asyncio
async def test_an_ai_failure_keeps_the_flow_alive(db_path, monkeypatch):
    monkeypatch.setattr(
        content_generator,
        "analyze_style",
        AsyncMock(side_effect=AIGatewayTimeoutError("boom")),
    )
    _seed_examples(db_path, REQUIRED_EXAMPLES)
    message = _make_message()

    handled = await read_style_if_ready(message, db_path, TELEGRAM_ID, "ru", True)

    assert handled is True
    assert get_style_profile(db_path, TELEGRAM_ID) is None
    args, kwargs = message.answer.call_args
    assert args[0] == _enough_message(REQUIRED_EXAMPLES)
    assert kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_reading_the_style_costs_no_quota(db_path, monkeypatch):
    _mock_analyze(monkeypatch)
    _seed_examples(db_path, REQUIRED_EXAMPLES)

    await read_style_if_ready(_make_message(), db_path, TELEGRAM_ID, "ru", False)

    assert get_daily_count(db_path, TELEGRAM_ID) == 0


@pytest.mark.asyncio
async def test_an_existing_profile_is_never_overwritten_by_a_new_sample(db_path, monkeypatch):
    set_style_profile(db_path, TELEGRAM_ID, "старое резюме")
    analyze = _mock_analyze(monkeypatch, "новое резюме")
    _seed_examples(db_path, REQUIRED_EXAMPLES)

    await read_style_if_ready(_make_message(), db_path, TELEGRAM_ID, "ru", False)

    analyze.assert_not_awaited()
    assert get_style_profile(db_path, TELEGRAM_ID) == "старое резюме"


@pytest.mark.asyncio
async def test_the_keyboard_offers_the_chosen_topic_only_when_there_is_one(db_path, monkeypatch):
    _mock_analyze(monkeypatch)
    _seed_examples(db_path, REQUIRED_EXAMPLES)

    with_topic = _make_message()
    await read_style_if_ready(with_topic, db_path, TELEGRAM_ID, "ru", True)
    without_topic = _make_message()
    await read_style_if_ready(without_topic, db_path, TELEGRAM_ID, "ru", False)

    assert len(with_topic.answer.call_args.kwargs["reply_markup"].inline_keyboard) == 3
    assert len(without_topic.answer.call_args.kwargs["reply_markup"].inline_keyboard) == 2
