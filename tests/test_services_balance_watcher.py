from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from bot.services import ai_gateway, balance_watcher
from bot.services.ai_gateway import AIGatewayUnavailableError
from bot.services.balance_watcher import BalanceWatcher

IMAGE_MODEL = "img-flux/flux-2-klein-4b"
STT_MODEL = "stt-openai/gpt-4o-mini-transcribe"


def _make_watcher(threshold: float = 50.0) -> tuple[BalanceWatcher, AsyncMock]:
    bot = AsyncMock()
    watcher = BalanceWatcher(bot, owner_chat_id=42, threshold_rub=threshold,
                             image_model=IMAGE_MODEL, transcription_model=STT_MODEL)
    return watcher, bot


@pytest.mark.asyncio
async def test_no_warning_while_balance_is_above_threshold(monkeypatch):
    watcher, bot = _make_watcher()
    monkeypatch.setattr(ai_gateway, "get_balance", AsyncMock(return_value=500.0))

    await watcher.check()

    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_warns_owner_when_balance_drops_below_threshold(monkeypatch):
    watcher, bot = _make_watcher(threshold=50.0)
    monkeypatch.setattr(ai_gateway, "get_balance", AsyncMock(return_value=12.34))

    await watcher.check()

    bot.send_message.assert_awaited_once()
    chat_id, text = bot.send_message.await_args.args
    assert chat_id == 42
    assert "12.34" in text
    # The owner needs to know what the remaining money actually buys, and that
    # the tariff does not cover usage — that misunderstanding is what caused
    # the outage in the first place.
    assert "картинок" in text
    assert "минут" in text
    assert "тариф" in text.lower()


@pytest.mark.asyncio
async def test_warns_only_once_while_balance_stays_low(monkeypatch):
    watcher, bot = _make_watcher()
    monkeypatch.setattr(ai_gateway, "get_balance", AsyncMock(return_value=5.0))

    await watcher.check()
    await watcher.check()
    await watcher.check()

    bot.send_message.assert_awaited_once()


@pytest.mark.asyncio
async def test_warns_again_after_balance_recovers_and_drops_once_more(monkeypatch):
    watcher, bot = _make_watcher(threshold=50.0)
    balances = AsyncMock(side_effect=[5.0, 500.0, 4.0])
    monkeypatch.setattr(ai_gateway, "get_balance", balances)

    await watcher.check()
    await watcher.check()
    await watcher.check()

    assert bot.send_message.await_count == 2


@pytest.mark.asyncio
async def test_balance_check_failure_is_swallowed(monkeypatch):
    watcher, bot = _make_watcher()
    monkeypatch.setattr(
        ai_gateway,
        "get_balance",
        AsyncMock(side_effect=AIGatewayUnavailableError("proxy down")),
    )

    await watcher.check()

    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_exactly_at_threshold_is_not_a_warning(monkeypatch):
    watcher, bot = _make_watcher(threshold=50.0)
    monkeypatch.setattr(ai_gateway, "get_balance", AsyncMock(return_value=50.0))

    await watcher.check()

    bot.send_message.assert_not_awaited()


def test_build_balance_scheduler_registers_a_job():
    bot = AsyncMock()
    scheduler = balance_watcher.build_balance_scheduler(
        bot,
        owner_chat_id=42,
        threshold_rub=50.0,
        interval_seconds=3600,
        image_model=IMAGE_MODEL,
        transcription_model=STT_MODEL,
    )

    job = scheduler.get_job("balance_check")
    assert job is not None
    assert job.trigger.interval.total_seconds() == 3600
