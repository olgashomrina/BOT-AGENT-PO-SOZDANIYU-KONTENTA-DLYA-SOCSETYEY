from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from apscheduler.triggers.cron import CronTrigger

from bot.services import digest as digest_service
from bot.services.digest_scheduler import _send_daily_digests, build_digest_scheduler
from bot.storage.users import set_digest_topic, set_interface_language
from bot.storage.whitelist import add_user


def test_build_digest_scheduler_registers_daily_cron_job(db_path):
    bot = AsyncMock()

    scheduler = build_digest_scheduler(bot, db_path, hour=9)

    jobs = scheduler.get_jobs()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.id == "daily_digest"
    assert isinstance(job.trigger, CronTrigger)
    assert str(job.trigger.timezone) == "Europe/Moscow"


@pytest.mark.asyncio
async def test_send_daily_digests_skips_non_whitelisted_users(db_path, monkeypatch):
    set_digest_topic(db_path, 111, "психология")  # never whitelisted
    mock_build = AsyncMock()
    monkeypatch.setattr(digest_service, "build_digest", mock_build)
    bot = AsyncMock()

    await _send_daily_digests(bot, db_path)

    mock_build.assert_not_awaited()
    bot.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_send_daily_digests_sends_to_whitelisted_users_with_topic(db_path, monkeypatch):
    add_user(db_path, 222)
    set_digest_topic(db_path, 222, "бухгалтерский учёт")
    set_interface_language(db_path, 222, "en")
    fake_result = digest_service.DigestResult(
        topic="бухгалтерский учёт", news=[], papers=[], methods_summary=None
    )
    mock_build = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(digest_service, "build_digest", mock_build)
    bot = AsyncMock()

    await _send_daily_digests(bot, db_path)

    mock_build.assert_awaited_once_with("бухгалтерский учёт")
    bot.send_message.assert_awaited_once_with(
        222, digest_service.format_digest_message(fake_result, "en")
    )


@pytest.mark.asyncio
async def test_send_daily_digests_continues_after_one_user_fails(db_path, monkeypatch):
    add_user(db_path, 333)
    add_user(db_path, 444)
    set_digest_topic(db_path, 333, "дизайн")
    set_digest_topic(db_path, 444, "строительство")

    async def _build(topic: str):
        if topic == "дизайн":
            raise RuntimeError("boom")
        return digest_service.DigestResult(topic=topic, news=[], papers=[], methods_summary=None)

    monkeypatch.setattr(digest_service, "build_digest", _build)
    bot = AsyncMock()

    await _send_daily_digests(bot, db_path)

    bot.send_message.assert_awaited_once()
    assert bot.send_message.await_args.args[0] == 444
