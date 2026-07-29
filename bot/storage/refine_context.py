from __future__ import annotations

from datetime import datetime, timezone

from bot.storage.db import get_connection

# Telegram keeps inline buttons alive on old messages indefinitely, so this
# table would otherwise grow without bound. The cap is per chat and generous
# enough that a user would have to generate hundreds of posts in one chat
# before the oldest buttons stop working — at which point regenerating from a
# months-old message is not a use case worth the storage.
MAX_CONTEXTS_PER_CHAT = 200


def save_refine_context(
    db_path: str,
    chat_id: int,
    message_id: int,
    source_text: str,
    content_language: str,
    with_hashtags: bool,
    platform: str,
) -> None:
    connection = get_connection(db_path)
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        # UPSERT rather than plain INSERT: a message id is unique per chat, but
        # re-saving the same one must not raise — it simply means the same
        # variant message was recorded twice.
        connection.execute(
            "INSERT INTO refine_contexts "
            "(chat_id, message_id, source_text, content_language, with_hashtags, platform, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT (chat_id, message_id) DO UPDATE SET "
            "source_text = excluded.source_text, "
            "content_language = excluded.content_language, "
            "with_hashtags = excluded.with_hashtags, "
            "platform = excluded.platform, "
            "created_at = excluded.created_at",
            (
                chat_id,
                message_id,
                source_text,
                content_language,
                int(with_hashtags),
                platform,
                created_at,
            ),
        )
        # Eviction keyed on id (insertion order), not created_at: sqlite's TEXT
        # timestamp cannot disambiguate two inserts inside the same clock tick,
        # but AUTOINCREMENT id always can. Same reasoning as
        # bot/storage/style_examples.py.
        connection.execute(
            "DELETE FROM refine_contexts WHERE chat_id = ? AND id NOT IN ("
            "SELECT id FROM refine_contexts WHERE chat_id = ? ORDER BY id DESC LIMIT ?)",
            (chat_id, chat_id, MAX_CONTEXTS_PER_CHAT),
        )
        connection.commit()
    finally:
        connection.close()


def get_refine_context(db_path: str, chat_id: int, message_id: int) -> dict | None:
    connection = get_connection(db_path)
    try:
        row = connection.execute(
            "SELECT source_text, content_language, with_hashtags, platform "
            "FROM refine_contexts WHERE chat_id = ? AND message_id = ?",
            (chat_id, message_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "source_text": row[0],
            "content_language": row[1],
            # sqlite has no bool type: the column round-trips as 0/1, and
            # callers pass this straight to the generator, which treats it as
            # a bool. Convert here so no caller has to remember.
            "with_hashtags": bool(row[2]),
            "platform": row[3],
        }
    finally:
        connection.close()
