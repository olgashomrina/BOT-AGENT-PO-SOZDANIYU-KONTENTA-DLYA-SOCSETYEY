from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from bot.storage.db import get_connection


@dataclass(frozen=True)
class SiteContent:
    text: str
    photo_file_id: str | None
    photo_static_path: str | None
    updated_at: str


def upsert_site_content(
    db_path: str,
    page: str,
    block_id: str,
    text: str,
    photo_file_id: str | None,
    photo_static_path: str | None,
) -> None:
    connection = get_connection(db_path)
    try:
        connection.execute(
            "INSERT INTO site_content (page, block_id, text, photo_file_id, photo_static_path, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(page, block_id) DO UPDATE SET "
            "text = excluded.text, photo_file_id = excluded.photo_file_id, "
            "photo_static_path = excluded.photo_static_path, updated_at = excluded.updated_at",
            (page, block_id, text, photo_file_id, photo_static_path, datetime.now(timezone.utc).isoformat()),
        )
        connection.commit()
    finally:
        connection.close()


def get_site_content(db_path: str, page: str, block_id: str) -> SiteContent | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT text, photo_file_id, photo_static_path, updated_at "
            "FROM site_content WHERE page = ? AND block_id = ?",
            (page, block_id),
        ).fetchone()
        if row is None:
            return None
        return SiteContent(text=row[0], photo_file_id=row[1], photo_static_path=row[2], updated_at=row[3])
    finally:
        connection.close()
