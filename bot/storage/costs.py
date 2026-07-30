"""Ledger of what the bot spent, per user, in rubles.

Exists to answer one question the owner needs before selling a subscription:
what does one active user actually cost per month? Recorded amounts come from
`bot/services/cost_tracker.py` — a price snapshot of the vsegpt.ru catalog,
not an invoice from the provider, so treat totals as close estimates rather
than accounting truth.
"""

from __future__ import annotations

from datetime import datetime, timezone

from bot.storage.db import get_connection


def _resolve_now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(timezone.utc)


def record_cost(
    db_path: str,
    telegram_id: int,
    operation: str,
    model: str,
    cost_rub: float,
    now: datetime | None = None,
) -> None:
    connection = get_connection(db_path)
    try:
        connection.execute(
            """
            INSERT INTO cost_log (telegram_id, occurred_at, operation, model, cost_rub)
            VALUES (?, ?, ?, ?, ?)
            """,
            (telegram_id, _resolve_now(now).isoformat(), operation, model, cost_rub),
        )
        connection.commit()
    finally:
        connection.close()


def get_monthly_total(db_path: str, now: datetime | None = None) -> float:
    month_prefix = _resolve_now(now).strftime("%Y-%m")
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT COALESCE(SUM(cost_rub), 0) FROM cost_log WHERE occurred_at LIKE ?",
            (f"{month_prefix}-%",),
        ).fetchone()
        return float(row[0])
    finally:
        connection.close()


def get_monthly_cost_by_user(
    db_path: str, now: datetime | None = None
) -> list[tuple[int, float]]:
    """Per-user spend for the current calendar month, biggest spender first."""
    month_prefix = _resolve_now(now).strftime("%Y-%m")
    connection = get_connection(db_path)
    try:
        rows = connection.execute(
            """
            SELECT telegram_id, SUM(cost_rub) AS total
            FROM cost_log
            WHERE occurred_at LIKE ?
            GROUP BY telegram_id
            ORDER BY total DESC
            """,
            (f"{month_prefix}-%",),
        ).fetchall()
        return [(row[0], float(row[1])) for row in rows]
    finally:
        connection.close()


def get_monthly_cost_by_operation(
    db_path: str, now: datetime | None = None
) -> list[tuple[str, float]]:
    """Spend split by operation, so it is obvious where the money goes."""
    month_prefix = _resolve_now(now).strftime("%Y-%m")
    connection = get_connection(db_path)
    try:
        rows = connection.execute(
            """
            SELECT operation, SUM(cost_rub) AS total
            FROM cost_log
            WHERE occurred_at LIKE ?
            GROUP BY operation
            ORDER BY total DESC
            """,
            (f"{month_prefix}-%",),
        ).fetchall()
        return [(row[0], float(row[1])) for row in rows]
    finally:
        connection.close()
