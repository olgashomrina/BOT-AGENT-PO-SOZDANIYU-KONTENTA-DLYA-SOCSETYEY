from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS whitelist (
    telegram_id INTEGER PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS users (
    telegram_id INTEGER PRIMARY KEY,
    interface_language TEXT,
    content_language TEXT,
    channel_id INTEGER,
    pending_media_file_id TEXT,
    pending_media_type TEXT
);

CREATE TABLE IF NOT EXISTS usage_log (
    telegram_id INTEGER NOT NULL,
    usage_date TEXT NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (telegram_id, usage_date)
);

CREATE TABLE IF NOT EXISTS style_examples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER NOT NULL,
    example_text TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def _ensure_channel_id_column(connection: sqlite3.Connection) -> None:
    # Phase 12 added this column after Phase 0-9 were already deployed in
    # production (Plan.md "Фаза 12"). CREATE TABLE IF NOT EXISTS above only
    # covers fresh installs — existing databases need an explicit migration
    # so the already-deployed bot doesn't crash on the next release.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    if "channel_id" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN channel_id INTEGER")


def _ensure_pending_media_columns(connection: sqlite3.Connection) -> None:
    # Phase 13 added these columns after Phases 0-12 were already deployed in
    # production (Plan.md "Фаза 13"). CREATE TABLE IF NOT EXISTS above only
    # covers fresh installs — existing databases need an explicit migration
    # so the already-deployed bot doesn't crash on the next release.
    columns = {row[1] for row in connection.execute("PRAGMA table_info(users)")}
    if "pending_media_file_id" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN pending_media_file_id TEXT")
    if "pending_media_type" not in columns:
        connection.execute("ALTER TABLE users ADD COLUMN pending_media_type TEXT")


def init_db(db_path: str) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(SCHEMA)
        _ensure_channel_id_column(connection)
        _ensure_pending_media_columns(connection)
        connection.commit()
    finally:
        connection.close()


def get_connection(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(db_path)
