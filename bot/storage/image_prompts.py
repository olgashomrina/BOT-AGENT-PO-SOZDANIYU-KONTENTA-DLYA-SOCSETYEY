from __future__ import annotations

from datetime import datetime, timezone

from bot.storage.db import get_connection

# Same rationale as bot/storage/refine_context.py: Telegram keeps inline
# buttons alive on old messages indefinitely, so this table would otherwise
# grow without bound.
MAX_PROMPTS_PER_CHAT = 200


def save_image_prompt(db_path: str, chat_id: int, message_id: int, prompt: str) -> None:
    connection = get_connection(db_path)
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO image_prompts (chat_id, message_id, prompt, created_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT (chat_id, message_id) DO UPDATE SET "
            "prompt = excluded.prompt, created_at = excluded.created_at",
            (chat_id, message_id, prompt, created_at),
        )
        connection.execute(
            "DELETE FROM image_prompts WHERE chat_id = ? AND id NOT IN ("
            "SELECT id FROM image_prompts WHERE chat_id = ? ORDER BY id DESC LIMIT ?)",
            (chat_id, chat_id, MAX_PROMPTS_PER_CHAT),
        )
        connection.commit()
    finally:
        connection.close()


def claim_image_prompt(db_path: str, chat_id: int, message_id: int) -> str | None:
    # Atomic read-and-delete via SQLite's DELETE...RETURNING: only one
    # caller can successfully claim a given (chat_id, message_id). A
    # concurrent second claim — e.g. a rapid double-tap on the same paid
    # button — finds the row already gone and must fall back to the
    # "missing context" path, instead of both callers billing the AI
    # Gateway for the same prompt.
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "DELETE FROM image_prompts WHERE chat_id = ? AND message_id = ? RETURNING prompt",
            (chat_id, message_id),
        ).fetchone()
        connection.commit()
        return row[0] if row else None
    finally:
        connection.close()
