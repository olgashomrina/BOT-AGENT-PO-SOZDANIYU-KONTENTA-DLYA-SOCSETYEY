from __future__ import annotations

from bot.storage.db import get_connection


def add_user(db_path: str, telegram_id: int) -> None:
    connection = get_connection(db_path)
    try:
        connection.execute(
            "INSERT OR IGNORE INTO whitelist (telegram_id) VALUES (?)",
            (telegram_id,),
        )
        connection.commit()
    finally:
        connection.close()


def remove_user(db_path: str, telegram_id: int) -> None:
    connection = get_connection(db_path)
    try:
        connection.execute(
            "DELETE FROM whitelist WHERE telegram_id = ?",
            (telegram_id,),
        )
        connection.commit()
    finally:
        connection.close()


def is_whitelisted(db_path: str, telegram_id: int) -> bool:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT 1 FROM whitelist WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        return row is not None
    finally:
        connection.close()
