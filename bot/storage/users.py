from __future__ import annotations

from bot.services import post_length
from bot.storage.db import get_connection


def _ensure_user_row(connection, telegram_id: int) -> None:
    connection.execute(
        "INSERT OR IGNORE INTO users (telegram_id, interface_language, content_language) "
        "VALUES (?, NULL, NULL)",
        (telegram_id,),
    )


def set_onboarding_shown(db_path: str, telegram_id: int, shown: bool) -> None:
    connection = get_connection(db_path)
    try:
        _ensure_user_row(connection, telegram_id)
        connection.execute(
            "UPDATE users SET onboarding_shown = ? WHERE telegram_id = ?",
            (1 if shown else 0, telegram_id),
        )
        connection.commit()
    finally:
        connection.close()


def get_onboarding_shown(db_path: str, telegram_id: int) -> bool:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT onboarding_shown FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        return bool(row[0]) if row and row[0] is not None else False
    finally:
        connection.close()


def set_channel_id(db_path: str, telegram_id: int, channel_id: int) -> None:
    connection = get_connection(db_path)
    try:
        _ensure_user_row(connection, telegram_id)
        connection.execute(
            "UPDATE users SET channel_id = ? WHERE telegram_id = ?",
            (channel_id, telegram_id),
        )
        connection.commit()
    finally:
        connection.close()


def get_channel_id(db_path: str, telegram_id: int) -> int | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT channel_id FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        return row[0] if row else None
    finally:
        connection.close()


def set_pending_media(db_path: str, telegram_id: int, file_id: str, media_type: str) -> None:
    connection = get_connection(db_path)
    try:
        _ensure_user_row(connection, telegram_id)
        connection.execute(
            "UPDATE users SET pending_media_file_id = ?, pending_media_type = ? "
            "WHERE telegram_id = ?",
            (file_id, media_type, telegram_id),
        )
        connection.commit()
    finally:
        connection.close()


def get_pending_media(db_path: str, telegram_id: int) -> tuple[str, str] | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT pending_media_file_id, pending_media_type FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        if row is None or row[0] is None or row[1] is None:
            return None
        return row[0], row[1]
    finally:
        connection.close()


def clear_pending_media(db_path: str, telegram_id: int) -> None:
    connection = get_connection(db_path)
    try:
        _ensure_user_row(connection, telegram_id)
        connection.execute(
            "UPDATE users SET pending_media_file_id = NULL, pending_media_type = NULL "
            "WHERE telegram_id = ?",
            (telegram_id,),
        )
        connection.commit()
    finally:
        connection.close()


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


def set_digest_topic(db_path: str, telegram_id: int, topic: str) -> None:
    connection = get_connection(db_path)
    try:
        _ensure_user_row(connection, telegram_id)
        connection.execute(
            "UPDATE users SET digest_topic = ? WHERE telegram_id = ?",
            (topic, telegram_id),
        )
        connection.commit()
    finally:
        connection.close()


def get_digest_topic(db_path: str, telegram_id: int) -> str | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT digest_topic FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        return row[0] if row else None
    finally:
        connection.close()


def get_users_with_digest_topic(db_path: str) -> list[tuple[int, str]]:
    connection = get_connection(db_path)
    try:
        rows = connection.execute(
            "SELECT telegram_id, digest_topic FROM users "
            "WHERE digest_topic IS NOT NULL AND digest_topic != ''"
        ).fetchall()
        return [(row[0], row[1]) for row in rows]
    finally:
        connection.close()


def set_post_length(db_path: str, telegram_id: int, preset: str) -> None:
    connection = get_connection(db_path)
    try:
        _ensure_user_row(connection, telegram_id)
        connection.execute(
            "UPDATE users SET post_length = ? WHERE telegram_id = ?",
            (preset, telegram_id),
        )
        connection.commit()
    finally:
        connection.close()


def get_post_length(db_path: str, telegram_id: int) -> str:
    """Всегда возвращает валидный ключ пресета, а не NULL и не мусор.

    Нормализация живёт здесь, чтобы три вызывающих хендлера не повторяли
    одну и ту же проверку. bot.services.post_length — модуль без зависимостей
    (только стандартная библиотека), поэтому импорт из storage цикла не создаёт.
    """
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT post_length FROM users WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        stored = row[0] if row else None
        return post_length.get_preset(stored).key
    finally:
        connection.close()
