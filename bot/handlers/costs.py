"""`/costs` — what the bot has spent this month, per user.

Owner-only, and Russian-only: this is a diagnostic for the person paying the
AI-proxy bill, not a user-facing feature, so it follows the same convention as
the owner crash notice in bot/main.py rather than going through the locale
files.

The point of the command is pricing a subscription. The per-user numbers are
the floor under any subscription price, and the per-operation split shows
which button is responsible (it is almost always the picture ones).
"""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import load_settings
from bot.logging_config import LOGGER_NAME
from bot.storage.costs import (
    get_monthly_cost_by_operation,
    get_monthly_cost_by_user,
    get_monthly_total,
)

logger = logging.getLogger(LOGGER_NAME)

router = Router(name="costs")

_NOT_OWNER = "Эта команда доступна только владельцу бота."

_NO_DATA = (
    "За этот месяц расходов на ИИ пока не записано.\n\n"
    "Учитываются картинки и расшифровка голосовых — текст постов стоит "
    "около 0.25 ₽ за цикл (меньше 5% расхода) и не детализируется."
)

_HEADER = "💰 Расходы на ИИ за текущий месяц: {total:.2f} ₽"

_FOOTER = (
    "\nЦены — снимок каталога vsegpt.ru на 30.07.2026 (подробности в "
    "dengi.md), а не выписка от провайдера: считайте это близкой оценкой. "
    "Текст постов не учитывается — это меньше 5% расхода."
)

_MAX_USERS_SHOWN = 15


@router.message(Command("costs"))
async def cmd_costs(message: Message, db_path: str) -> None:
    settings = load_settings()
    if message.from_user.id != settings.owner_chat_id:
        await message.answer(_NOT_OWNER)
        return

    total = get_monthly_total(db_path)
    if total <= 0:
        await message.answer(_NO_DATA)
        return

    by_user = get_monthly_cost_by_user(db_path)
    by_operation = get_monthly_cost_by_operation(db_path)

    lines = [_HEADER.format(total=total), "", "По операциям:"]
    lines.extend(f"• {operation}: {cost:.2f} ₽" for operation, cost in by_operation)
    lines.extend(["", f"По пользователям (всего {len(by_user)}):"])
    lines.extend(
        f"• {telegram_id}: {cost:.2f} ₽" for telegram_id, cost in by_user[:_MAX_USERS_SHOWN]
    )
    if len(by_user) > _MAX_USERS_SHOWN:
        lines.append(f"…и ещё {len(by_user) - _MAX_USERS_SHOWN}")
    lines.append(_FOOTER)

    logger.info(
        "Owner requested cost report",
        extra={"user_id": message.from_user.id, "operation": "handler:costs"},
    )
    await message.answer("\n".join(lines))
