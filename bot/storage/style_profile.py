from __future__ import annotations

from datetime import datetime, timezone

from bot.storage.db import get_connection


def set_style_profile(db_path: str, telegram_id: int, summary: str) -> None:
    created_at = datetime.now(timezone.utc).isoformat()
    connection = get_connection(db_path)
    try:
        connection.execute(
            "INSERT OR REPLACE INTO style_profiles (telegram_id, summary, created_at) "
            "VALUES (?, ?, ?)",
            (telegram_id, summary, created_at),
        )
        connection.commit()
    finally:
        connection.close()


def get_style_profile(db_path: str, telegram_id: int) -> str | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT summary FROM style_profiles WHERE telegram_id = ?",
            (telegram_id,),
        ).fetchone()
        return row[0] if row else None
    finally:
        connection.close()


def clear_style_profile(db_path: str, telegram_id: int) -> None:
    # Called together with clear_style_examples: a profile that outlived the
    # samples it was read from would describe posts the bot no longer has, and
    # would also stop a fresh set of samples from ever being analysed.
    connection = get_connection(db_path)
    try:
        connection.execute(
            "DELETE FROM style_profiles WHERE telegram_id = ?", (telegram_id,)
        )
        connection.commit()
    finally:
        connection.close()
