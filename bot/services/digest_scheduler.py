from __future__ import annotations

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.locales.loader import DEFAULT_LANGUAGE
from bot.logging_config import LOGGER_NAME
from bot.services import digest
from bot.storage.users import get_interface_language, get_users_with_digest_topic
from bot.storage.whitelist import is_whitelisted

logger = logging.getLogger(LOGGER_NAME)


async def _send_daily_digests(bot: Bot, db_path: str) -> None:
    for telegram_id, topic in get_users_with_digest_topic(db_path):
        if not is_whitelisted(db_path, telegram_id):
            continue

        language = get_interface_language(db_path, telegram_id) or DEFAULT_LANGUAGE
        try:
            result = await digest.build_digest(topic)
            await bot.send_message(telegram_id, digest.format_digest_message(result, language))
        except Exception:
            logger.warning(
                "Daily digest failed for user",
                extra={"user_id": telegram_id, "operation": "daily_digest"},
                exc_info=True,
            )


def build_digest_scheduler(bot: Bot, db_path: str, hour: int) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _send_daily_digests,
        trigger=CronTrigger(hour=hour, minute=0, timezone="Europe/Moscow"),
        args=[bot, db_path],
        id="daily_digest",
    )
    return scheduler
