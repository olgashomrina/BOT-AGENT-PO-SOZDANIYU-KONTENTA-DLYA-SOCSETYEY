from __future__ import annotations

import asyncio

from aiogram import Bot, Dispatcher

from bot.config import load_settings
from bot.handlers.start import router as start_router
from bot.logging_config import setup_logging


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.include_router(start_router)
    return dispatcher


async def run() -> None:
    settings = load_settings()
    logger = setup_logging(level=settings.log_level)

    bot = Bot(token=settings.bot_token)
    dispatcher = build_dispatcher()

    logger.info("Бот запускается (long polling)")
    try:
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
