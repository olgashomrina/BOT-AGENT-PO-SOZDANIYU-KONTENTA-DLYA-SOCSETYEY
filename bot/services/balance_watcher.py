"""Warns the owner before the AI-proxy balance runs out.

The failure this prevents actually happened on 2026-07-30: the balance hit
zero unnoticed and voice transcription simply stopped working, which read as
a bug in the bot rather than as an empty account (see dengi.md). A paid
vsegpt.ru tariff does not prepay usage — every call is billed against the
balance — so nothing except an explicit check tells the owner it is running
low.

The warning fires once per crossing, not once per check: a balance that sits
below the threshold for a week must not produce a message every hour. It
re-arms as soon as the balance goes back above the threshold.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from bot.logging_config import LOGGER_NAME
from bot.services import ai_gateway, cost_tracker
from bot.services.ai_gateway import AIGatewayError
from bot.services.owner_notifier import notify_owner

logger = logging.getLogger(LOGGER_NAME)


def _format_warning(
    balance: float, threshold: float, image_model: str, transcription_model: str
) -> str:
    images = cost_tracker.images_affordable(balance, image_model)
    minutes = cost_tracker.voice_minutes_affordable(balance, transcription_model)
    return (
        f"⚠️ Баланс AI-прокси заканчивается: {balance:.2f} ₽ "
        f"(порог предупреждения — {threshold:.0f} ₽).\n\n"
        f"Этого хватит примерно на {images} картинок или {minutes} минут "
        "расшифровки голосовых.\n\n"
        "Важно: тариф на vsegpt.ru снимает лимиты на частоту запросов, но "
        "использование API не оплачивает — его нужно пополнять отдельно. "
        "Когда баланс дойдёт до нуля, бот перестанет расшифровывать голосовые "
        "и генерировать картинки."
    )


class BalanceWatcher:
    """Checks the balance on a schedule and warns the owner once per crossing."""

    def __init__(
        self,
        bot: Bot,
        owner_chat_id: int,
        threshold_rub: float,
        image_model: str,
        transcription_model: str,
    ) -> None:
        self._bot = bot
        self._owner_chat_id = owner_chat_id
        self._threshold_rub = threshold_rub
        self._image_model = image_model
        self._transcription_model = transcription_model
        self._warned = False

    async def check(self) -> None:
        try:
            balance = await ai_gateway.get_balance()
        except AIGatewayError:
            # An unreachable or unrecognisable balance endpoint must never take
            # the bot down or spam the owner — the AI Gateway has already
            # logged the details, including the raw body, which is how the
            # real response shape gets pinned down from production.
            logger.warning(
                "Balance check failed",
                extra={"operation": "balance_check"},
                exc_info=True,
            )
            return

        if balance >= self._threshold_rub:
            self._warned = False
            return

        if self._warned:
            return

        logger.warning(
            "AI proxy balance below alert threshold",
            extra={
                "operation": "balance_check",
                "balance_rub": balance,
                "threshold_rub": self._threshold_rub,
            },
        )
        await notify_owner(
            self._bot,
            self._owner_chat_id,
            _format_warning(
                balance, self._threshold_rub, self._image_model, self._transcription_model
            ),
        )
        self._warned = True


def build_balance_scheduler(
    bot: Bot,
    owner_chat_id: int,
    threshold_rub: float,
    interval_seconds: int,
    image_model: str,
    transcription_model: str,
) -> AsyncIOScheduler:
    watcher = BalanceWatcher(
        bot, owner_chat_id, threshold_rub, image_model, transcription_model
    )
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        watcher.check,
        trigger=IntervalTrigger(seconds=interval_seconds),
        id="balance_check",
        # Same reasoning as the digest scheduler: a busy event loop must not
        # make APScheduler skip the check entirely.
        misfire_grace_time=interval_seconds,
        # IntervalTrigger's first fire would otherwise be a whole interval
        # away — an hour by default. Checking immediately means a bot
        # restarted on an empty balance says so at once.
        next_run_time=datetime.now(timezone.utc),
    )
    return scheduler
