from __future__ import annotations

import asyncio
import sys

from aiogram import Bot, Dispatcher

from bot.config import load_settings
from bot.handlers.channel import router as channel_router
from bot.handlers.content import router as content_router
from bot.handlers.errors import router as errors_router
from bot.handlers.language import router as language_router
from bot.handlers.refine import router as refine_router
from bot.handlers.start import router as start_router
from bot.logging_config import setup_logging
from bot.middlewares.rate_limit_middleware import RateLimitMiddleware
from bot.middlewares.whitelist_middleware import WhitelistMiddleware
from bot.services.owner_notifier import notify_owner
from bot.storage.db import init_db

_OWNER_CRASH_NOTICE = (
    "Бот остановился из-за непредвиденной ошибки и не отвечает. "
    "Сервер должен перезапустить его автоматически — если бот не "
    "восстановится сам в течение нескольких минут, обратитесь к "
    "разработчику. Подробности в логах на сервере."
)


def build_dispatcher(daily_limit: int, monthly_limit: int) -> Dispatcher:
    dispatcher = Dispatcher()
    # Whitelist gating must run before the rate-limit middleware consumes a
    # usage slot, otherwise uninvited users could exhaust other users' quota.
    dispatcher.message.outer_middleware(WhitelistMiddleware())
    dispatcher.message.outer_middleware(RateLimitMiddleware(daily_limit, monthly_limit))
    dispatcher.include_router(start_router)
    dispatcher.include_router(language_router)
    dispatcher.include_router(channel_router)
    dispatcher.include_router(content_router)
    dispatcher.include_router(refine_router)
    # Registered last: per-request errors are already handled locally inside
    # the routers above (Plan.md 5.1/5.2). This is only the safety net for
    # whatever a handler did not catch itself (bugs, unforeseen exceptions).
    dispatcher.include_router(errors_router)
    return dispatcher


async def run() -> None:
    settings = load_settings()
    logger = setup_logging(level=settings.log_level)
    init_db(settings.db_path)

    bot = Bot(token=settings.bot_token)
    dispatcher = build_dispatcher(settings.daily_limit, settings.monthly_limit)

    logger.info("Бот запускается (long polling)")
    try:
        await dispatcher.start_polling(bot, db_path=settings.db_path)
    except Exception:
        # Process-level crash, distinct from per-request errors (which never
        # reach here — bot/handlers/errors.py catches those). Nothing left
        # to do for this request/process but log loudly, tell the owner,
        # and let it propagate so main() exits non-zero for systemd.
        logger.critical("Процесс бота аварийно завершается", exc_info=True)
        try:
            await notify_owner(bot, settings.owner_chat_id, _OWNER_CRASH_NOTICE)
        except Exception:
            logger.critical("Не удалось уведомить владельца о падении бота", exc_info=True)
        raise
    finally:
        await bot.session.close()


def main() -> None:
    try:
        asyncio.run(run())
    except Exception:
        # Non-zero exit so systemd's Restart=on-failure actually restarts
        # the process (deploy/systemd/content-bot.service) — must not be
        # swallowed into a clean exit.
        sys.exit(1)


if __name__ == "__main__":
    main()
