from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from bot.storage.db import get_connection

# Донор короче аудио приходится зацикливать, и на стыке видна склейка —
# кадр дёргается, кружок сразу читается как подделка. 20 секунд — жёсткий
# минимум приёма, 35 — то, что просим у пользователя в тексте приглашения.
MIN_DONOR_SECONDS = 20
RECOMMENDED_DONOR_SECONDS = 35

# Меньше трёх доноров — один и тот же фон в каждом кружке, подписчики
# замечают повтор быстрее, чем кажется.
MIN_DONOR_COUNT = 3


@dataclass(frozen=True)
class Donor:
    id: int
    file_id: str
    duration_sec: int
    transcript: str | None


def add_donor(
    db_path: str,
    telegram_id: int,
    file_id: str,
    duration_sec: int,
    transcript: str | None,
) -> int:
    connection = get_connection(db_path)
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        cursor = connection.execute(
            "INSERT INTO avatar_donors "
            "(telegram_id, file_id, duration_sec, transcript, created_at, is_active) "
            "VALUES (?, ?, ?, ?, ?, 1)",
            (telegram_id, file_id, duration_sec, transcript, created_at),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def get_donors(db_path: str, telegram_id: int) -> list[Donor]:
    connection = get_connection(db_path)
    try:
        rows = connection.execute(
            "SELECT id, file_id, duration_sec, transcript FROM avatar_donors "
            "WHERE telegram_id = ? AND is_active = 1 ORDER BY id ASC",
            (telegram_id,),
        ).fetchall()
        return [
            Donor(id=row[0], file_id=row[1], duration_sec=row[2], transcript=row[3])
            for row in rows
        ]
    finally:
        connection.close()


def count_donors(db_path: str, telegram_id: int) -> int:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT COUNT(*) FROM avatar_donors WHERE telegram_id = ? AND is_active = 1",
            (telegram_id,),
        ).fetchone()
        return int(row[0])
    finally:
        connection.close()


def clear_donors(db_path: str, telegram_id: int) -> None:
    connection = get_connection(db_path)
    try:
        connection.execute(
            "DELETE FROM avatar_donors WHERE telegram_id = ?", (telegram_id,)
        )
        connection.commit()
    finally:
        connection.close()
