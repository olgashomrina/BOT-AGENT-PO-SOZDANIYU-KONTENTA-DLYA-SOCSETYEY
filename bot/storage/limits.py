from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from bot.storage.db import get_connection


class LimitStatus(Enum):
    OK = "ok"
    DAILY_EXCEEDED = "daily_exceeded"
    MONTHLY_EXCEEDED = "monthly_exceeded"


def _resolve_now(now: datetime | None) -> datetime:
    return now if now is not None else datetime.now(timezone.utc)


def increment_usage(db_path: str, telegram_id: int, now: datetime | None = None) -> None:
    usage_date = _resolve_now(now).strftime("%Y-%m-%d")
    connection = get_connection(db_path)
    try:
        connection.execute(
            """
            INSERT INTO usage_log (telegram_id, usage_date, request_count)
            VALUES (?, ?, 1)
            ON CONFLICT(telegram_id, usage_date)
            DO UPDATE SET request_count = request_count + 1
            """,
            (telegram_id, usage_date),
        )
        connection.commit()
    finally:
        connection.close()


def get_daily_count(db_path: str, telegram_id: int, now: datetime | None = None) -> int:
    usage_date = _resolve_now(now).strftime("%Y-%m-%d")
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT request_count FROM usage_log WHERE telegram_id = ? AND usage_date = ?",
            (telegram_id, usage_date),
        ).fetchone()
        return row[0] if row else 0
    finally:
        connection.close()


def get_monthly_count(db_path: str, telegram_id: int, now: datetime | None = None) -> int:
    month_prefix = _resolve_now(now).strftime("%Y-%m")
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT COALESCE(SUM(request_count), 0) FROM usage_log "
            "WHERE telegram_id = ? AND usage_date LIKE ?",
            (telegram_id, f"{month_prefix}-%"),
        ).fetchone()
        return row[0]
    finally:
        connection.close()


def check_limit_status(
    db_path: str,
    telegram_id: int,
    daily_limit: int,
    monthly_limit: int,
    now: datetime | None = None,
) -> LimitStatus:
    if get_daily_count(db_path, telegram_id, now) >= daily_limit:
        return LimitStatus.DAILY_EXCEEDED
    if get_monthly_count(db_path, telegram_id, now) >= monthly_limit:
        return LimitStatus.MONTHLY_EXCEEDED
    return LimitStatus.OK
