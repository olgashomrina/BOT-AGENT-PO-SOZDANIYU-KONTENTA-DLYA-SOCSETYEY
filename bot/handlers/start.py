from __future__ import annotations

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

router = Router(name="start")

GREETING = (
    "Привет! Я бот-помощник для создания контента в соцсетях.\n\n"
    "Скоро я научусь превращать ссылки, голосовые сообщения и текст "
    "в готовые варианты постов для Telegram и VK. Пока я в разработке — "
    "эта команда работает как заглушка."
)


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    await message.answer(GREETING)
