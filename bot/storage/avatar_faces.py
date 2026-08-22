from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from bot.storage.db import get_connection


@dataclass(frozen=True)
class Face:
    file_id: str
    created_at: str


def save_face(db_path: str, telegram_id: int, file_id: str) -> None:
    # Лицо ровно одно на пользователя: замена перезаписывает строку.
    connection = get_connection(db_path)
    try:
        connection.execute(
            "INSERT INTO avatar_faces (telegram_id, file_id, created_at) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(telegram_id) DO UPDATE SET "
            "file_id = excluded.file_id, created_at = excluded.created_at",
            (telegram_id, file_id, datetime.now(timezone.utc).isoformat()),
        )
        connection.commit()
    finally:
        connection.close()


def get_face(db_path: str, telegram_id: int) -> Face | None:
    # Прочитать лицо пользователя, если оно сохранено.
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT file_id, created_at FROM avatar_faces WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        return None if row is None else Face(file_id=row[0], created_at=row[1])
    finally:
        connection.close()


def delete_face(db_path: str, telegram_id: int) -> None:
    # Удалить лицо пользователя.
    connection = get_connection(db_path)
    try:
        connection.execute(
            "DELETE FROM avatar_faces WHERE telegram_id = ?", (telegram_id,)
        )
        connection.commit()
    finally:
        connection.close()
