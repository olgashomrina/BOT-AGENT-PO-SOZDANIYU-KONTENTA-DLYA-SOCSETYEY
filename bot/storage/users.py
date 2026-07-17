from __future__ import annotations

from bot.storage.db import get_connection


def _ensure_user_row(connection, telegram_id: int) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO users (telegram_id, interface_language, content_language) "
        "VALUES (?, NULL, NULL)",
        (telegram_id,),
    )


def set_interface_language(db_path: str, telegram_id: int, language: str) -> None:
    connection = get_connection(db_path)
    try:
        _ensure_user_row(connection, telegram_id)
        connection.execute(
            "UPDATE users SET interface_language = ? WHERE telegram_id = ?",
            (language, telegram_id),
        )
        connection.commit()
    finally:
        connection.close()


def get_interface_language(db_path: str, telegram_id: int) -> str | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT interface_language FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        return row[0] if row else None
    finally:
        connection.close()


def set_content_language(db_path: str, telegram_id: int, language: str) -> None:
    connection = get_connection(db_path)
    try:
        _ensure_user_row(connection, telegram_id)
        connection.execute(
            "UPDATE users SET content_language = ? WHERE telegram_id = ?",
            (language, telegram_id),
        )
        connection.commit()
    finally:
        connection.close()


def get_content_language(db_path: str, telegram_id: int) -> str | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT interface_language, content_language FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if row is None:
            return None
        interface_language, content_language = row
        return content_language if content_language is not None else interface_language
    finally:
        connection.close()
