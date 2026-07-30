from __future__ import annotations

import asyncio
import sys

from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, MenuButtonCommands
from aiohttp import web

from bot.config import load_settings
from bot.handlers.authorpost import router as authorpost_router
from bot.handlers.channel import router as channel_router
from bot.handlers.content import router as content_router
from bot.handlers.costs import router as costs_router
from bot.handlers.errors import router as errors_router
from bot.handlers.language import router as language_router
from bot.handlers.refine import router as refine_router
from bot.handlers.settov import router as settov_router
from bot.handlers.site import router as site_router
from bot.handlers.start import router as start_router
from bot.locales.loader import SUPPORTED_LANGUAGES, get_string
from bot.logging_config import setup_logging
from bot.middlewares.rate_limit_middleware import RateLimitMiddleware
from bot.middlewares.whitelist_middleware import WhitelistMiddleware
from bot.services.balance_watcher import build_balance_scheduler
from bot.services.digest_scheduler import build_digest_scheduler
from bot.services.owner_notifier import notify_owner
from bot.services.site_api import build_site_api_app
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
    dispatcher.include_router(site_router)
    dispatcher.include_router(settov_router)
    # Before content_router, whose StateFilter(None) message handler would
    # otherwise swallow /costs as content input.
    dispatcher.include_router(costs_router)
    # Before content_router: its message handler is state-filtered to
    # AuthorPostStates.collecting_examples, and keeping the state-specific
    # router ahead of content_router's catch-all StateFilter(None) matches
    # how settov_router is already ordered.
    dispatcher.include_router(authorpost_router)
    dispatcher.include_router(content_router)
    dispatcher.include_router(refine_router)
    # Registered last: per-request errors are already handled locally inside
    # the routers above (Plan.md 5.1/5.2). This is only the safety net for
    # whatever a handler did not catch itself (bugs, unforeseen exceptions).
    dispatcher.include_router(errors_router)
    return dispatcher


async def _configure_start_menu_button(bot: Bot) -> None:
    # Native Telegram "menu button" (bottom-left of the input field) is
    # rendered by the client itself, before the user has ever messaged the
    # bot — unlike our reply-keyboard "Старт" button, which only appears
    # after the bot has sent it in response to a message.
    for lang in SUPPORTED_LANGUAGES:
        await bot.set_my_commands(
            [BotCommand(command="start", description=get_string("command_start_description", lang))],
            language_code=lang,
        )
    await bot.set_chat_menu_button(menu_button=MenuButtonCommands())


async def run() -> None:
    settings = load_settings()
    logger = setup_logging(level=settings.log_level)
    init_db(settings.db_path)

    bot = Bot(token=settings.bot_token)
    await _configure_start_menu_button(bot)
    dispatcher = build_dispatcher(settings.daily_limit, settings.monthly_limit)

    digest_scheduler = build_digest_scheduler(bot, settings.db_path, settings.digest_send_hour)
    digest_scheduler.start()

    balance_scheduler = build_balance_scheduler(
        bot,
        settings.owner_chat_id,
        settings.balance_alert_threshold_rub,
        settings.balance_check_interval_seconds,
        settings.ai_gateway_image_model,
        settings.ai_gateway_transcription_model,
    )
    balance_scheduler.start()

    site_api_app = build_site_api_app(settings.db_path, settings.site_media_dir)
    runner = web.AppRunner(site_api_app)
    await runner.setup()
    site = web.TCPSite(runner, settings.site_api_host, settings.site_api_port)
    await site.start()

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
        digest_scheduler.shutdown()
        balance_scheduler.shutdown()
        await runner.cleanup()
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
