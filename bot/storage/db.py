from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS whitelist (
    telegram_id INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    interface_language TEXT,
    content_language TEXT
);

CREATE TABLE IF NOT EXISTS usage_log (
    telegram_id INTEGER NOT NULL,
    usage_date TEXT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (telegram_id, usage_date)
);
"""


def init_db(db_path: str) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(SCHEMA)
        connection.commit()
    finally:
        connection.close()


def get_connection(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(db_path)
