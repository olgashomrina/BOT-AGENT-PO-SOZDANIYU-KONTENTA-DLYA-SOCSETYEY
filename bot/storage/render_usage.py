"""Сколько секунд рендера и рублей потратил каждый пользователь за месяц.

Отдельно от `usage_log` и `cost_log` намеренно. `usage_log` считает обращения,
и рендер в тех же единицах не меряется: один кружок стоит как несколько сотен
текстовых генераций. `cost_log` — общая летопись расходов для отчёта; здесь
же лежит счётчик, по которому принимается решение «пускать или отказать»,
и ему нужен быстрый ответ по одному ключу.
"""

from __future__ import annotations

from datetime import datetime, timezone

from bot.storage.db import get_connection


def _resolve_month(now: datetime | None) -> str:
    moment = now if now is not None else datetime.now(timezone.utc)
    return moment.strftime("%Y-%m")


def add_usage(
    db_path: str,
    telegram_id: int,
    seconds: int,
    cost_rub: float,
    now: datetime | None = None,
) -> None:
    """Прибавить секунды и рубли к счётчику месяца.

    `seconds` бывает и отрицательным: секунды бронируются при запуске рендера
    и возвращаются, если рендер не состоялся. Счётчик при этом не должен
    уходить ниже нуля — отрицательный расход выдал бы пользователю лимит
    больше положенного.
    """
    connection = get_connection(db_path)
    try:
        connection.execute(
            "INSERT INTO render_usage "
            "(telegram_id, usage_month, seconds_rendered, cost_rub) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(telegram_id, usage_month) DO UPDATE SET "
            "seconds_rendered = MAX(0, seconds_rendered + excluded.seconds_rendered), "
            "cost_rub = cost_rub + excluded.cost_rub",
            (telegram_id, _resolve_month(now), seconds, cost_rub),
        )
        connection.commit()
    finally:
        connection.close()


def get_month_seconds(
    db_path: str, telegram_id: int, now: datetime | None = None
) -> int:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT seconds_rendered FROM render_usage "
            "WHERE telegram_id = ? AND usage_month = ?",
            (telegram_id, _resolve_month(now)),
        ).fetchone()
        # Строка могла быть создана сразу возвратом брони (рендер сорвался
        # раньше, чем счётчик появился) — наружу такой счётчик уходит нулём.
        return max(0, int(row[0])) if row else 0
    finally:
        connection.close()


def seconds_left(
    db_path: str, telegram_id: int, limit: int, now: datetime | None = None
) -> int:
    return max(0, limit - get_month_seconds(db_path, telegram_id, now=now))
