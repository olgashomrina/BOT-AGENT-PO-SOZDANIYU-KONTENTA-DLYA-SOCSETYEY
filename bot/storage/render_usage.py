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

    Ноль стережётся в обеих ветках, и в новой строке тоже. Бронь месяца N
    возвращается иногда уже в месяце N+1 (рендер шёл через полночь первого
    числа): такой возврат создаёт строку следующего месяца, и родись она
    отрицательной, первые же настоящие секунды пользователя ушли бы в её
    минус — оплаченные и не посчитанные. Отдельная `MAX(0, ?)` в `VALUES`
    нужна потому, что вычитать из уже существующей строки по-прежнему надо
    полной величиной: `excluded` для этого не годится.

    Известное и не закрытое здесь ограничение того же происхождения: `-30`
    возврата всё равно уходит в месяц N+1, а не туда, откуда бронь на самом
    деле бралась. Если в N+1 уже есть настоящий расход, пользователь получит
    от чужого провала на границе месяца 30 секунд лимита, которых не
    зарабатывал, а месяц N так и останется с висящей бронью, которую больше
    никто не вернёт. Починить это по-настоящему можно только храня месяц
    брони на самом задании, а это правка схемы, которая сейчас не делается.
    """
    connection = get_connection(db_path)
    try:
        connection.execute(
            "INSERT INTO render_usage "
            "(telegram_id, usage_month, seconds_rendered, cost_rub) "
            "VALUES (?, ?, MAX(0, ?), ?) "
            "ON CONFLICT(telegram_id, usage_month) DO UPDATE SET "
            "seconds_rendered = MAX(0, seconds_rendered + ?), "
            "cost_rub = cost_rub + excluded.cost_rub",
            (telegram_id, _resolve_month(now), seconds, cost_rub, seconds),
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
        # Запись минус уже не пропускает, но в базе могли остаться строки,
        # созданные возвратом брони до этого; наружу они уходят нулём.
        return max(0, int(row[0])) if row else 0
    finally:
        connection.close()


def seconds_left(
    db_path: str, telegram_id: int, limit: int, now: datetime | None = None
) -> int:
    return max(0, limit - get_month_seconds(db_path, telegram_id, now=now))
