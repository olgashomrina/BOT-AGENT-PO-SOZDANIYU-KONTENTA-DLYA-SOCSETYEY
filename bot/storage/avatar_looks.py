from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from bot.storage.db import get_connection

# Присланная пользователем картинка и картинка, которую бот собрал из лица
# по описанию, ведут себя одинаково при рендере, но по-разному объясняются
# в интерфейсе: у второй есть промпт, который можно показать и повторить.
SOURCE_UPLOADED = "uploaded"
SOURCE_GENERATED = "generated"

_FIELDS = "id, file_id, title, source, prompt, is_active, created_at"


@dataclass(frozen=True)
class Look:
    id: int
    file_id: str
    title: str
    source: str
    prompt: str | None
    is_active: bool
    created_at: str


def _row_to_look(row: tuple) -> Look:
    return Look(
        id=row[0],
        file_id=row[1],
        title=row[2],
        source=row[3],
        prompt=row[4],
        is_active=bool(row[5]),
        created_at=row[6],
    )


def add_look(
    db_path: str,
    telegram_id: int,
    file_id: str,
    title: str,
    source: str,
    prompt: str | None = None,
) -> int:
    connection = get_connection(db_path)
    try:
        has_active = connection.execute(
            "SELECT 1 FROM avatar_looks WHERE telegram_id = ? AND is_active = 1",
            (telegram_id,),
        ).fetchone()
        cursor = connection.execute(
            "INSERT INTO avatar_looks "
            "(telegram_id, file_id, title, source, prompt, is_active, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                telegram_id,
                file_id,
                title,
                source,
                prompt,
                0 if has_active else 1,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def get_looks(db_path: str, telegram_id: int) -> list[Look]:
    connection = get_connection(db_path)
    try:
        rows = connection.execute(
            f"SELECT {_FIELDS} FROM avatar_looks WHERE telegram_id = ? ORDER BY id ASC",
            (telegram_id,),
        ).fetchall()
        return [_row_to_look(row) for row in rows]
    finally:
        connection.close()


def get_look(db_path: str, telegram_id: int, look_id: int) -> Look | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            f"SELECT {_FIELDS} FROM avatar_looks WHERE telegram_id = ? AND id = ?",
            (telegram_id, look_id),
        ).fetchone()
        return None if row is None else _row_to_look(row)
    finally:
        connection.close()


def get_active_look(db_path: str, telegram_id: int) -> Look | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            f"SELECT {_FIELDS} FROM avatar_looks "
            "WHERE telegram_id = ? AND is_active = 1",
            (telegram_id,),
        ).fetchone()
        return None if row is None else _row_to_look(row)
    finally:
        connection.close()


def count_looks(db_path: str, telegram_id: int) -> int:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT COUNT(*) FROM avatar_looks WHERE telegram_id = ?", (telegram_id,)
        ).fetchone()
        return int(row[0])
    finally:
        connection.close()


def set_active_look(db_path: str, telegram_id: int, look_id: int) -> None:
    # Снятие и установка флага — одна транзакция: между ними база не должна
    # быть видна ни с двумя активными образами, ни с нулём.
    connection = get_connection(db_path)
    try:
        connection.execute(
            "UPDATE avatar_looks SET is_active = 0 WHERE telegram_id = ?",
            (telegram_id,),
        )
        connection.execute(
            "UPDATE avatar_looks SET is_active = 1 WHERE telegram_id = ? AND id = ?",
            (telegram_id, look_id),
        )
        connection.commit()
    finally:
        connection.close()


def delete_look(db_path: str, telegram_id: int, look_id: int) -> None:
    connection = get_connection(db_path)
    try:
        connection.execute(
            "DELETE FROM avatar_looks WHERE telegram_id = ? AND id = ?",
            (telegram_id, look_id),
        )
        orphaned = connection.execute(
            "SELECT 1 FROM avatar_looks WHERE telegram_id = ? AND is_active = 1",
            (telegram_id,),
        ).fetchone()
        if orphaned is None:
            # Удалили активный образ — активным становится самый свежий из
            # оставшихся. Иначе следующая речь упрётся в «образа нет», хотя
            # образы у пользователя есть.
            connection.execute(
                "UPDATE avatar_looks SET is_active = 1 WHERE id = ("
                "SELECT id FROM avatar_looks WHERE telegram_id = ? "
                "ORDER BY id DESC LIMIT 1)",
                (telegram_id,),
            )
        connection.commit()
    finally:
        connection.close()


def clear_looks(db_path: str, telegram_id: int) -> None:
    connection = get_connection(db_path)
    try:
        connection.execute(
            "DELETE FROM avatar_looks WHERE telegram_id = ?", (telegram_id,)
        )
        connection.commit()
    finally:
        connection.close()
