from __future__ import annotations

import sqlite3

from bot.storage.db import init_db


def _columns(path: str, table: str) -> set[str]:
    connection = sqlite3.connect(path)
    try:
        return {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
    finally:
        connection.close()


def test_avatar_donors_table_created(db_path):
    assert _columns(db_path, "avatar_donors") == {
        "id",
        "telegram_id",
        "file_id",
        "duration_sec",
        "transcript",
        "created_at",
        "last_used_at",
        "is_active",
    }


def test_voice_profiles_table_created(db_path):
    assert _columns(db_path, "voice_profiles") == {
        "telegram_id",
        "provider",
        "external_voice_id",
        "consent_at",
        "created_at",
    }


def test_style_examples_gains_kind_column(db_path):
    assert "kind" in _columns(db_path, "style_examples")


def test_kind_column_is_added_to_legacy_database(tmp_path):
    # Воспроизводим базу, развёрнутую до этой фичи: style_examples без kind.
    path = str(tmp_path / "legacy.db")
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE style_examples ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_id INTEGER NOT NULL, "
        "example_text TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    connection.execute(
        "INSERT INTO style_examples (telegram_id, example_text, created_at) "
        "VALUES (?, ?, ?)",
        (1, "Старый пост", "2026-07-01T00:00:00+00:00"),
    )
    connection.commit()
    connection.close()

    init_db(path)

    connection = sqlite3.connect(path)
    try:
        rows = connection.execute("SELECT kind FROM style_examples").fetchall()
    finally:
        connection.close()
    assert rows == [("written",)]


def test_init_db_is_idempotent(db_path):
    init_db(db_path)

    assert "kind" in _columns(db_path, "style_examples")
