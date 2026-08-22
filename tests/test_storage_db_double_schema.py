from __future__ import annotations

import sqlite3

from bot.storage.db import get_connection, init_db


def _columns(path: str, table: str) -> set[str]:
    connection = get_connection(path)
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


def test_avatar_faces_table_holds_one_row_per_user(db_path):
    assert _columns(db_path, "avatar_faces") == {
        "telegram_id",
        "file_id",
        "created_at",
    }


def test_avatar_looks_table_has_activity_flag(db_path):
    assert _columns(db_path, "avatar_looks") == {
        "id",
        "telegram_id",
        "file_id",
        "title",
        "source",
        "prompt",
        "is_active",
        "created_at",
    }


def test_speech_jobs_table_carries_money_and_format(db_path):
    assert _columns(db_path, "speech_jobs") == {
        "id",
        "telegram_id",
        "source_text",
        "script",
        "look_id",
        "audio_path",
        "audio_duration_sec",
        "format",
        "status",
        "provider_task_id",
        "result_file_id",
        "cost_rub",
        "error",
        "created_at",
        "updated_at",
    }


def test_render_usage_is_keyed_by_user_and_month(db_path):
    assert _columns(db_path, "render_usage") == {
        "telegram_id",
        "usage_month",
        "seconds_rendered",
        "cost_rub",
    }


def test_init_db_is_idempotent_on_an_existing_database(db_path):
    # Развёрнутая база уже существует: повторный init_db не должен ни падать,
    # ни стирать данные. Это и есть вся миграция для новых таблиц.
    connection = get_connection(db_path)
    try:
        connection.execute(
            "INSERT INTO avatar_faces (telegram_id, file_id, created_at) VALUES (1, 'f', 'now')"
        )
        connection.commit()
    finally:
        connection.close()

    init_db(db_path)

    connection = get_connection(db_path)
    try:
        row = connection.execute("SELECT file_id FROM avatar_faces").fetchone()
    finally:
        connection.close()
    assert row[0] == "f"
