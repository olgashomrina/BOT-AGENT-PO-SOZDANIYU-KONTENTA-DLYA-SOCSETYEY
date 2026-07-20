from __future__ import annotations

from datetime import datetime, timezone

from bot.storage.db import get_connection

# Plan.md Phase 14: "лимит на количество (старые вытесняются)" — keep only
# the most recent MAX_EXAMPLES_PER_USER examples per user, evicting older
# ones on every insert.
MAX_EXAMPLES_PER_USER = 5


def add_style_example(db_path: str, telegram_id: int, text: str) -> None:
    connection = get_connection(db_path)
    try:
        created_at = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO style_examples (telegram_id, example_text, created_at) "
            "VALUES (?, ?, ?)",
            (telegram_id, text, created_at),
        )
        # Eviction keyed on id (insertion order), not created_at: sqlite's
        # TEXT timestamp column can't disambiguate two inserts within the
        # same wall-clock resolution, but AUTOINCREMENT id always does.
        connection.execute(
            "DELETE FROM style_examples WHERE telegram_id = ? AND id NOT IN ("
            "SELECT id FROM style_examples WHERE telegram_id = ? "
            "ORDER BY id DESC LIMIT ?)",
            (telegram_id, telegram_id, MAX_EXAMPLES_PER_USER),
        )
        connection.commit()
    finally:
        connection.close()


def get_style_examples(
    db_path: str, telegram_id: int, limit: int = MAX_EXAMPLES_PER_USER
) -> list[str]:
    # Most-recent-first (id DESC): the newest examples are the most likely
    # to still reflect the user's current voice, and this is also the order
    # they get quoted into the generation prompt (content_generator.py).
    connection = get_connection(db_path)
    try:
        rows = connection.execute(
            "SELECT example_text FROM style_examples WHERE telegram_id = ? "
            "ORDER BY id DESC LIMIT ?",
            (telegram_id, limit),
        ).fetchall()
        return [row[0] for row in rows]
    finally:
        connection.close()
