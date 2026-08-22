from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from bot.storage.db import get_connection

STATUS_DRAFT = "draft"
STATUS_VOICED = "voiced"
STATUS_RENDERING = "rendering"
STATUS_READY = "ready"
STATUS_PUBLISHED = "published"
STATUS_FAILED = "failed"

# Задание закончено, когда ролик опубликован или сгорел. Всё остальное —
# незавершённая работа, к которой пользователь может вернуться.
_TERMINAL_STATUSES = (STATUS_PUBLISHED, STATUS_FAILED)

FORMAT_VIDEO_NOTE = "video_note"

# Колонки, которые вправе менять `update_job`. Список закрытый: имя поля
# приходит из кода как строка, и опечатка иначе прошла бы молча.
_UPDATABLE = frozenset(
    {
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
    }
)

_FIELDS = (
    "id, telegram_id, source_text, script, look_id, audio_path, "
    "audio_duration_sec, format, status, provider_task_id, result_file_id, "
    "cost_rub, error, created_at, updated_at"
)


@dataclass(frozen=True)
class SpeechJob:
    id: int
    telegram_id: int
    source_text: str
    script: str | None
    look_id: int | None
    audio_path: str | None
    audio_duration_sec: float | None
    format: str
    status: str
    provider_task_id: str | None
    result_file_id: str | None
    cost_rub: float | None
    error: str | None
    created_at: str
    updated_at: str


def _row_to_job(row: tuple) -> SpeechJob:
    return SpeechJob(*row)


def create_job(db_path: str, telegram_id: int, source_text: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    connection = get_connection(db_path)
    try:
        cursor = connection.execute(
            "INSERT INTO speech_jobs "
            "(telegram_id, source_text, format, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (telegram_id, source_text, FORMAT_VIDEO_NOTE, STATUS_DRAFT, now, now),
        )
        connection.commit()
        return int(cursor.lastrowid)
    finally:
        connection.close()


def get_job(db_path: str, job_id: int) -> SpeechJob | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            f"SELECT {_FIELDS} FROM speech_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        return None if row is None else _row_to_job(row)
    finally:
        connection.close()


def get_active_job(db_path: str, telegram_id: int) -> SpeechJob | None:
    placeholders = ", ".join("?" for _ in _TERMINAL_STATUSES)
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            f"SELECT {_FIELDS} FROM speech_jobs WHERE telegram_id = ? "
            f"AND status NOT IN ({placeholders}) ORDER BY id DESC LIMIT 1",
            (telegram_id, *_TERMINAL_STATUSES),
        ).fetchone()
        return None if row is None else _row_to_job(row)
    finally:
        connection.close()


def get_jobs_by_status(db_path: str, status: str) -> list[SpeechJob]:
    connection = get_connection(db_path)
    try:
        rows = connection.execute(
            f"SELECT {_FIELDS} FROM speech_jobs WHERE status = ? ORDER BY id ASC",
            (status,),
        ).fetchall()
        return [_row_to_job(row) for row in rows]
    finally:
        connection.close()


def update_job(db_path: str, job_id: int, **fields) -> None:
    unknown = set(fields) - _UPDATABLE
    if unknown:
        raise ValueError(f"Неизвестные поля задания: {sorted(unknown)}")
    if not fields:
        return

    assignments = ", ".join(f"{name} = ?" for name in fields)
    connection = get_connection(db_path)
    try:
        connection.execute(
            f"UPDATE speech_jobs SET {assignments}, updated_at = ? WHERE id = ?",
            (*fields.values(), datetime.now(timezone.utc).isoformat(), job_id),
        )
        connection.commit()
    finally:
        connection.close()
