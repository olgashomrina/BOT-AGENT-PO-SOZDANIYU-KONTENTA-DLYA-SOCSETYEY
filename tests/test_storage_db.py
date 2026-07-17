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
