from __future__ import annotations

import sqlite3

from bot.storage.db import get_connection, init_db


def _table_names(path: str) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        return {row[0] for row in rows}
    finally:
        connection.close()


def test_init_db_creates_expected_tables(tmp_path):
    path = str(tmp_path / "fresh.db")

    init_db(path)

    tables = _table_names(path)
    assert {"users", "whitelist", "usage_log"}.issubset(tables)


def test_init_db_is_idempotent(tmp_path):
    path = str(tmp_path / "fresh.db")

    init_db(path)
    init_db(path)

    tables = _table_names(path)
    assert {"users", "whitelist", "usage_log"}.issubset(tables)


def test_get_connection_returns_usable_connection(db_path):
    connection = get_connection(db_path)
    try:
        connection.execute("SELECT 1")
    finally:
        connection.close()


def test_init_db_migrates_pre_phase12_users_table(tmp_path):
    path = str(tmp_path / "legacy.db")

    connection = sqlite3.connect(path)
    try:
        connection.execute(
            """
            CREATE TABLE users (
                telegram_id INTEGER PRIMARY KEY,
                interface_language TEXT,
                content_language TEXT
            )
            """
        )
        connection.execute(
            "INSERT INTO users (telegram_id, interface_language, content_language) "
            "VALUES (?, ?, ?)",
            (42, "ru", "en"),
        )
        connection.commit()
    finally:
        connection.close()

    init_db(path)

    connection = sqlite3.connect(path)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
        assert "channel_id" in columns

        row = connection.execute(
            "SELECT telegram_id, interface_language, content_language, channel_id "
            "FROM users WHERE telegram_id = ?",
            (42,),
        ).fetchone()
        assert row == (42, "ru", "en", None)
    finally:
        connection.close()

    init_db(path)

    connection = sqlite3.connect(path)
    try:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
        assert "channel_id" in columns
        row = connection.execute(
            "SELECT telegram_id, interface_language, content_language, channel_id "
            "FROM users WHERE telegram_id = ?",
            (42,),
        ).fetchone()
        assert row == (42, "ru", "en", None)
    finally:
        connection.close()
